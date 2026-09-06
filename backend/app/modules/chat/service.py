"""Логика каналов и сообщений.

Доступ к каналу определяется подтверждённой квартирой пользователя:
квартира → подъезд → дом → ЖК. Отдельного вступления не требуется —
жилец сразу видит каналы своего дома.
"""

import base64
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.modules.auth.models import User
from app.modules.chat.models import (
    Channel,
    ChannelMember,
    Message,
    MessageAttachment,
    MessageRead,
)
from app.modules.chat.schemas import AuthorOut, MessageIn
from app.modules.properties.models import Apartment, Building, Complex, Entrance
from app.modules.residents.models import ApartmentResident
from app.shared.enums import ChannelType, ResidentStatus

log = structlog.get_logger(__name__)

DEFAULT_CHANNELS: list[tuple[ChannelType, str, bool]] = [
    (ChannelType.ANNOUNCEMENTS, "Объявления ОСИ", True),
    (ChannelType.COMPLEX, "Чат дома", False),
    (ChannelType.MARKETPLACE, "Барахолка", False),
]


def _encode_cursor(value: datetime) -> str:
    return base64.urlsafe_b64encode(value.isoformat().encode()).decode()


def _decode_cursor(cursor: str) -> datetime:
    try:
        return datetime.fromisoformat(base64.urlsafe_b64decode(cursor.encode()).decode())
    except Exception as exc:  # noqa: BLE001
        raise ValidationError("Некорректный курсор постраничной загрузки") from exc


class ChatService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Каналы
    # ------------------------------------------------------------------

    async def ensure_default_channels(self, complex_id: uuid.UUID) -> list[Channel]:
        """Создаёт базовый набор каналов ЖК при первом обращении."""
        existing = list(
            (
                await self.session.scalars(
                    select(Channel).where(
                        Channel.complex_id == complex_id, Channel.entrance_id.is_(None)
                    )
                )
            ).all()
        )
        present = {c.type for c in existing}

        for channel_type, name, readonly in DEFAULT_CHANNELS:
            if channel_type in present:
                continue
            channel = Channel(
                complex_id=complex_id, type=channel_type, name=name, is_readonly=readonly
            )
            self.session.add(channel)
            existing.append(channel)

        await self.session.flush()
        return existing

    async def _user_scope(
        self, user_id: uuid.UUID
    ) -> tuple[set[uuid.UUID], set[uuid.UUID], set[uuid.UUID]]:
        """ЖК, дома и подъезды, доступные пользователю по подтверждённым квартирам."""
        rows = await self.session.execute(
            select(Complex.id, Building.id, Entrance.id)
            .join(Building, Building.complex_id == Complex.id)
            .join(Entrance, Entrance.building_id == Building.id)
            .join(Apartment, Apartment.entrance_id == Entrance.id)
            .join(ApartmentResident, ApartmentResident.apartment_id == Apartment.id)
            .where(
                ApartmentResident.user_id == user_id,
                ApartmentResident.status == ResidentStatus.VERIFIED,
            )
        )
        complexes: set[uuid.UUID] = set()
        buildings: set[uuid.UUID] = set()
        entrances: set[uuid.UUID] = set()
        for cx, bd, en in rows.all():
            complexes.add(cx)
            buildings.add(bd)
            entrances.add(en)
        return complexes, buildings, entrances

    async def list_channels(self, user: User) -> list[Channel]:
        complexes, buildings, entrances = await self._user_scope(user.id)
        if not complexes:
            return []

        for complex_id in complexes:
            await self.ensure_default_channels(complex_id)

        result = await self.session.scalars(
            select(Channel)
            .where(
                Channel.is_active.is_(True),
                Channel.complex_id.in_(complexes),
                or_(
                    Channel.entrance_id.is_(None) & Channel.building_id.is_(None),
                    Channel.building_id.in_(buildings) if buildings else False,
                    Channel.entrance_id.in_(entrances) if entrances else False,
                ),
            )
            .order_by(Channel.type)
        )
        return list(result.all())

    async def get_channel(self, channel_id: uuid.UUID) -> Channel:
        channel = await self.session.get(Channel, channel_id)
        if channel is None or not channel.is_active:
            raise NotFoundError("Канал не найден")
        return channel

    async def can_read(self, user_id: uuid.UUID, channel: Channel, is_staff: bool = False) -> bool:
        """Сотрудник организации видит каналы своих ЖК, даже не имея там квартиры."""
        if is_staff:
            return True
        complexes, buildings, entrances = await self._user_scope(user_id)
        if channel.complex_id not in complexes:
            return False
        if channel.entrance_id and channel.entrance_id not in entrances:
            return False
        if channel.building_id and channel.building_id not in buildings:
            return False
        return True

    async def can_write(self, user: User, channel: Channel, is_staff: bool) -> bool:
        if channel.is_readonly and not is_staff:
            return False
        member = await self.session.scalar(
            select(ChannelMember).where(
                ChannelMember.channel_id == channel.id, ChannelMember.user_id == user.id
            )
        )
        if member and member.muted_until and member.muted_until > datetime.now(UTC):
            return False
        return True

    async def channel_organization(self, channel: Channel) -> uuid.UUID:
        organization_id = await self.session.scalar(
            select(Complex.organization_id).where(Complex.id == channel.complex_id)
        )
        if organization_id is None:
            raise NotFoundError("Организация канала не найдена")
        return organization_id

    # ------------------------------------------------------------------
    # Сообщения
    # ------------------------------------------------------------------

    async def list_messages(
        self, channel_id: uuid.UUID, limit: int = 30, cursor: str | None = None
    ) -> tuple[list[tuple[Message, User]], str | None]:
        query = (
            select(Message, User)
            .join(User, Message.author_id == User.id)
            .where(Message.channel_id == channel_id)
            .order_by(Message.created_at.desc())
            .limit(limit + 1)
        )
        if cursor:
            query = query.where(Message.created_at < _decode_cursor(cursor))

        rows = (await self.session.execute(query)).all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = _encode_cursor(rows[-1][0].created_at) if has_more and rows else None
        return [(r[0], r[1]) for r in rows], next_cursor

    async def create_message(
        self, channel_id: uuid.UUID, author: User, payload: MessageIn
    ) -> Message:
        if not payload.text and not payload.attachments:
            raise ValidationError("Сообщение не может быть пустым")

        message = Message(
            channel_id=channel_id,
            author_id=author.id,
            text=payload.text,
            reply_to_id=payload.reply_to_id,
            is_important=payload.is_important,
            is_pinned=payload.is_important,
        )
        self.session.add(message)
        await self.session.flush()

        for item in payload.attachments:
            self.session.add(MessageAttachment(message_id=message.id, **item.model_dump()))

        await self.session.flush()
        await self.session.refresh(message)
        return message

    async def delete_message(self, message_id: uuid.UUID, actor: User, is_staff: bool) -> Message:
        message = await self.session.get(Message, message_id)
        if message is None:
            raise NotFoundError("Сообщение не найдено")
        if message.author_id != actor.id and not is_staff:
            raise PermissionDeniedError("Удалить сообщение может автор или модератор")

        message.deleted_at = datetime.now(UTC)
        message.deleted_by = actor.id
        message.text = None
        await self.session.flush()
        return message

    async def mute_member(
        self, channel_id: uuid.UUID, user_id: uuid.UUID, hours: int
    ) -> ChannelMember:
        member = await self.session.scalar(
            select(ChannelMember).where(
                ChannelMember.channel_id == channel_id, ChannelMember.user_id == user_id
            )
        )
        if member is None:
            member = ChannelMember(channel_id=channel_id, user_id=user_id)
            self.session.add(member)

        member.muted_until = datetime.now(UTC) + timedelta(hours=hours)
        await self.session.flush()
        return member

    # ------------------------------------------------------------------
    # Прочтения
    # ------------------------------------------------------------------

    async def mark_read(
        self, channel_id: uuid.UUID, user_id: uuid.UUID, moment: datetime | None
    ) -> None:
        moment = moment or datetime.now(UTC)
        record = await self.session.scalar(
            select(MessageRead).where(
                MessageRead.channel_id == channel_id, MessageRead.user_id == user_id
            )
        )
        if record is None:
            self.session.add(
                MessageRead(channel_id=channel_id, user_id=user_id, last_read_at=moment)
            )
        else:
            record.last_read_at = max(record.last_read_at, moment)
        await self.session.flush()

    async def unread_counts(
        self, user_id: uuid.UUID, channel_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        if not channel_ids:
            return {}

        reads = {
            r.channel_id: r.last_read_at
            for r in await self.session.scalars(
                select(MessageRead).where(
                    MessageRead.user_id == user_id, MessageRead.channel_id.in_(channel_ids)
                )
            )
        }
        counts: dict[uuid.UUID, int] = {}
        for channel_id in channel_ids:
            conditions = [
                Message.channel_id == channel_id,
                Message.deleted_at.is_(None),
                # Собственные сообщения непрочитанными не считаются
                Message.author_id != user_id,
            ]
            since = reads.get(channel_id)
            if since is not None:
                conditions.append(Message.created_at > since)

            unread = await self.session.scalar(select(func.count(Message.id)).where(*conditions))
            counts[channel_id] = int(unread or 0)
        return counts

    async def last_messages(
        self, channel_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[Message, User]]:
        if not channel_ids:
            return {}
        result: dict[uuid.UUID, tuple[Message, User]] = {}
        for channel_id in channel_ids:
            row = (
                await self.session.execute(
                    select(Message, User)
                    .join(User, Message.author_id == User.id)
                    .where(Message.channel_id == channel_id, Message.deleted_at.is_(None))
                    .order_by(Message.created_at.desc())
                    .limit(1)
                )
            ).first()
            if row:
                result[channel_id] = (row[0], row[1])
        return result

    @staticmethod
    def author_out(user: User) -> AuthorOut:
        return AuthorOut(id=user.id, name=user.full_name, avatar_url=user.avatar_url)
