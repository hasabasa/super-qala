"""Фоновые задачи arq."""

from datetime import UTC, date, datetime
from typing import Any

import structlog
from sqlalchemy import select

# Импорт реестра моделей обязателен: воркер не поднимает роутеры,
# и без него метаданные SQLAlchemy знают лишь часть таблиц, из-за чего
# внешние ключи не разрешаются.
import app.models  # noqa: F401
from app.core.db import SessionFactory
from app.modules.billing.models import Invoice
from app.modules.notifications.service import NotificationService
from app.shared.enums import InvoiceStatus

log = structlog.get_logger(__name__)


async def deliver_notifications(_: dict[str, Any]) -> int:
    """Рассылает накопившиеся уведомления."""
    async with SessionFactory() as session:
        sent = await NotificationService(session).deliver_pending()
        await session.commit()
        return sent


async def mark_overdue_invoices(_: dict[str, Any]) -> int:
    """Переводит просроченные квитанции в соответствующий статус."""
    async with SessionFactory() as session:
        today = date.today()
        invoices = await session.scalars(
            select(Invoice).where(
                Invoice.status.in_([InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID]),
                Invoice.due_date < today,
            )
        )
        count = 0
        for invoice in invoices:
            invoice.status = InvoiceStatus.OVERDUE
            count += 1
        await session.commit()
        if count:
            log.info("billing.marked_overdue", count=count)
        return count


async def remind_payment_due(_: dict[str, Any]) -> int:
    """Напоминает об оплате за три дня до срока."""
    from datetime import timedelta

    from app.modules.billing.models import Account
    from app.modules.residents.models import ApartmentResident
    from app.shared.enums import NotificationType, ResidentStatus

    async with SessionFactory() as session:
        target = date.today() + timedelta(days=3)
        rows = await session.execute(
            select(Invoice, ApartmentResident.user_id)
            .join(Account, Invoice.account_id == Account.id)
            .join(ApartmentResident, ApartmentResident.apartment_id == Account.apartment_id)
            .where(
                Invoice.due_date == target,
                Invoice.status.in_([InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID]),
                ApartmentResident.status == ResidentStatus.VERIFIED,
            )
        )
        service = NotificationService(session)
        count = 0
        for invoice, user_id in rows.all():
            await service.notify(
                user_id,
                NotificationType.PAYMENT_DUE_SOON,
                "Скоро срок оплаты",
                f"Квитанция на {invoice.outstanding} ₸ — оплатить до {invoice.due_date:%d.%m.%Y}",
                {"type": "invoice", "id": str(invoice.id)},
            )
            count += 1
        await session.commit()
        return count


async def cleanup_orphan_files(_: dict[str, Any]) -> int:
    """Удаляет файлы, загруженные, но так и не привязанные к объекту."""
    from app.modules.files.service import FilesService

    async with SessionFactory() as session:
        removed = await FilesService(session).cleanup_orphans()
        await session.commit()
        return removed


async def startup(ctx: dict[str, Any]) -> None:
    log.info("worker.started", at=datetime.now(UTC).isoformat())


async def shutdown(ctx: dict[str, Any]) -> None:
    log.info("worker.stopped")
