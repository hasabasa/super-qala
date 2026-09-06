"""Создание и отправка уведомлений.

Другие модули вызывают notify() и ничего не знают ни про FCM,
ни про устройства пользователя.
"""

import base64
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.modules.notifications.models import (
    Device,
    Notification,
    NotificationPreference,
)
from app.modules.notifications.schemas import DeviceIn
from app.modules.notifications.sender import get_push_sender
from app.shared.enums import NotificationStatus, NotificationType

log = structlog.get_logger(__name__)


def _encode_cursor(value: datetime) -> str:
    return base64.urlsafe_b64encode(value.isoformat().encode()).decode()


def _decode_cursor(cursor: str) -> datetime:
    try:
        return datetime.fromisoformat(base64.urlsafe_b64decode(cursor.encode()).decode())
    except Exception as exc:  # noqa: BLE001
        raise ValidationError("Некорректный курсор") from exc


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Устройства
    # ------------------------------------------------------------------

    async def register_device(self, user_id: uuid.UUID, payload: DeviceIn) -> Device:
        """Один токен принадлежит одному пользователю: при переустановке
        или смене аккаунта он переезжает, а не дублируется."""
        device = await self.session.scalar(
            select(Device).where(Device.fcm_token == payload.fcm_token)
        )
        if device is None:
            device = Device(user_id=user_id, **payload.model_dump())
            self.session.add(device)
        else:
            device.user_id = user_id
            device.platform = payload.platform
            device.app_version = payload.app_version
            device.locale = payload.locale
            device.is_active = True

        device.last_seen_at = datetime.now(UTC)
        await self.session.flush()
        return device

    async def unregister_device(self, user_id: uuid.UUID, token: str) -> None:
        device = await self.session.scalar(
            select(Device).where(Device.fcm_token == token, Device.user_id == user_id)
        )
        if device is not None:
            device.is_active = False
            await self.session.flush()

    # ------------------------------------------------------------------
    # Создание уведомлений
    # ------------------------------------------------------------------

    async def notify(
        self,
        user_id: uuid.UUID,
        notification_type: NotificationType,
        title: str,
        body: str,
        payload: dict[str, Any] | None = None,
    ) -> Notification:
        notification = Notification(
            user_id=user_id,
            type=notification_type,
            title=title,
            body=body,
            payload=payload,
        )
        self.session.add(notification)
        await self.session.flush()
        return notification

    async def notify_many(
        self,
        user_ids: list[uuid.UUID],
        notification_type: NotificationType,
        title: str,
        body: str,
        payload: dict[str, Any] | None = None,
    ) -> list[Notification]:
        created: list[Notification] = []
        for user_id in dict.fromkeys(user_ids):
            created.append(await self.notify(user_id, notification_type, title, body, payload))
        return created

    # ------------------------------------------------------------------
    # Отправка
    # ------------------------------------------------------------------

    async def deliver_pending(self, limit: int = 500) -> int:
        """Отправляет накопившиеся уведомления. Вызывается фоновой задачей."""
        pending = list(
            (
                await self.session.scalars(
                    select(Notification)
                    .where(Notification.status == NotificationStatus.PENDING)
                    .order_by(Notification.created_at)
                    .limit(limit)
                )
            ).all()
        )
        if not pending:
            return 0

        sender = get_push_sender()
        sent = 0
        for notification in pending:
            if not await self._is_enabled(notification.user_id, notification.type):
                notification.status = NotificationStatus.SKIPPED
                continue

            tokens = list(
                (
                    await self.session.scalars(
                        select(Device.fcm_token).where(
                            Device.user_id == notification.user_id,
                            Device.is_active.is_(True),
                        )
                    )
                ).all()
            )
            if not tokens:
                # Уведомление остаётся в истории и будет видно в приложении
                notification.status = NotificationStatus.SKIPPED
                continue

            result = await sender.send(
                tokens, notification.title, notification.body, notification.payload
            )
            if result.success:
                notification.status = NotificationStatus.SENT
                notification.sent_at = datetime.now(UTC)
                sent += 1
            else:
                notification.status = NotificationStatus.FAILED
                notification.error = result.error

            for token in result.invalid_tokens:
                device = await self.session.scalar(
                    select(Device).where(Device.fcm_token == token)
                )
                if device is not None:
                    device.is_active = False

        await self.session.flush()
        log.info("notifications.delivered", total=len(pending), sent=sent)
        return sent

    async def _is_enabled(self, user_id: uuid.UUID, notification_type: str) -> bool:
        preference = await self.session.scalar(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id,
                NotificationPreference.type == notification_type,
            )
        )
        return preference is None or preference.push_enabled

    # ------------------------------------------------------------------
    # Чтение
    # ------------------------------------------------------------------

    async def list_for_user(
        self, user_id: uuid.UUID, limit: int = 30, cursor: str | None = None
    ) -> tuple[list[Notification], str | None, int]:
        query = (
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit + 1)
        )
        if cursor:
            query = query.where(Notification.created_at < _decode_cursor(cursor))

        rows = list((await self.session.scalars(query)).all())
        has_more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = _encode_cursor(rows[-1].created_at) if has_more and rows else None

        unread = await self.session.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_id, Notification.read_at.is_(None)
            )
        )
        return rows, next_cursor, int(unread or 0)

    async def mark_read(self, user_id: uuid.UUID, notification_ids: list[uuid.UUID] | None) -> int:
        query = select(Notification).where(
            Notification.user_id == user_id, Notification.read_at.is_(None)
        )
        if notification_ids:
            query = query.where(Notification.id.in_(notification_ids))

        now = datetime.now(UTC)
        count = 0
        for notification in await self.session.scalars(query):
            notification.read_at = now
            count += 1
        await self.session.flush()
        return count

    async def set_preference(
        self, user_id: uuid.UUID, notification_type: str, enabled: bool
    ) -> NotificationPreference:
        preference = await self.session.scalar(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id,
                NotificationPreference.type == notification_type,
            )
        )
        if preference is None:
            preference = NotificationPreference(user_id=user_id, type=notification_type)
            self.session.add(preference)
        preference.push_enabled = enabled
        await self.session.flush()
        return preference

    async def list_preferences(self, user_id: uuid.UUID) -> dict[str, bool]:
        stored = {
            p.type: p.push_enabled
            for p in await self.session.scalars(
                select(NotificationPreference).where(NotificationPreference.user_id == user_id)
            )
        }
        return {t.value: stored.get(t.value, True) for t in NotificationType}
