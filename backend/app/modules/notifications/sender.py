"""Отправка push-уведомлений.

Провайдер — Firebase Cloud Messaging. Пока учётные данные не заведены,
работает заглушка: уведомление помечается отправленным и пишется в лог.
"""

from dataclasses import dataclass
from typing import Any

import structlog

from app.core.config import settings

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class PushResult:
    success: bool
    error: str | None = None
    invalid_tokens: tuple[str, ...] = ()


class PushSender:
    async def send(
        self, tokens: list[str], title: str, body: str, payload: dict[str, Any] | None
    ) -> PushResult:
        raise NotImplementedError


class ConsolePushSender(PushSender):
    """Заглушка для разработки: ничего не отправляет, только логирует."""

    async def send(
        self, tokens: list[str], title: str, body: str, payload: dict[str, Any] | None
    ) -> PushResult:
        log.info("push.console", tokens=len(tokens), title=title, body=body, payload=payload)
        return PushResult(success=True)


class FirebasePushSender(PushSender):
    """Отправка через FCM. Подключается, когда появятся учётные данные."""

    async def send(
        self, tokens: list[str], title: str, body: str, payload: dict[str, Any] | None
    ) -> PushResult:
        raise NotImplementedError("Учётные данные Firebase не настроены")


def get_push_sender() -> PushSender:
    if settings.FCM_CREDENTIALS_PATH:
        return FirebasePushSender()
    return ConsolePushSender()
