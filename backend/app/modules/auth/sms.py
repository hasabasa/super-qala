"""Отправка SMS.

Провайдер выбирается настройкой SMS_PROVIDER. Локально работает console —
код печатается в лог, реальные сообщения не уходят.
"""

import structlog

from app.core.config import settings

log = structlog.get_logger(__name__)


class SmsProvider:
    async def send(self, phone: str, text: str) -> None:
        raise NotImplementedError


class ConsoleSmsProvider(SmsProvider):
    """Заглушка для локальной разработки."""

    async def send(self, phone: str, text: str) -> None:
        log.info("sms.console", phone=phone, text=text)


class SmscProvider(SmsProvider):
    """Заготовка под реального провайдера.

    Провайдер ещё не выбран — см. открытые блокеры в docs/CONTEXT.md.
    """

    async def send(self, phone: str, text: str) -> None:
        raise NotImplementedError("SMS-провайдер не подключён")


def get_sms_provider() -> SmsProvider:
    if settings.SMS_PROVIDER == "console":
        return ConsoleSmsProvider()
    return SmscProvider()
