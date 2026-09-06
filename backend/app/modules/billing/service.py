"""Начисления, квитанции, платежи и сверка.

Сверка устроена так: платёж из банковского реестра разносится по
неоплаченным квитанциям лицевого счёта, начиная с самой старой.
Люди платят не той суммой и сразу за несколько месяцев — это норма,
поэтому остаток платежа сохраняется и ждёт следующих начислений.
"""

import uuid
from datetime import UTC, date, datetime

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AccessScope
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from app.modules.billing.models import (
    Account,
    BillingPeriod,
    Charge,
    Invoice,
    PaymentClaim,
    PaymentFact,
    ReconciliationEntry,
    ServiceType,
)
from app.modules.billing.schemas import (
    AccountIn,
    BillingPeriodIn,
    ChargeImportIn,
    ChargeImportOut,
    PaymentClaimIn,
    PaymentRegistryImportIn,
    PaymentRegistryImportOut,
    ServiceTypeIn,
)
from app.modules.properties.models import Apartment, Building, Complex, Entrance
from app.shared.enums import (
    BillingPeriodStatus,
    InvoiceStatus,
    PaymentClaimStatus,
    PaymentFactSource,
    ReconciliationAction,
)

log = structlog.get_logger(__name__)


class BillingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Справочники
    # ------------------------------------------------------------------

    async def create_service_type(
        self, organization_id: uuid.UUID, payload: ServiceTypeIn
    ) -> ServiceType:
        exists = await self.session.scalar(
            select(ServiceType.id).where(
                ServiceType.organization_id == organization_id,
                ServiceType.name == payload.name,
            )
        )
        if exists:
            raise ConflictError("Такая услуга уже заведена")

        service_type = ServiceType(organization_id=organization_id, **payload.model_dump())
        self.session.add(service_type)
        await self.session.flush()
        return service_type

    async def list_service_types(self, organization_id: uuid.UUID) -> list[ServiceType]:
        result = await self.session.scalars(
            select(ServiceType)
            .where(
                ServiceType.organization_id == organization_id,
                ServiceType.is_active.is_(True),
            )
            .order_by(ServiceType.order_num, ServiceType.name)
        )
        return list(result.all())

    async def create_account(self, organization_id: uuid.UUID, payload: AccountIn) -> Account:
        exists = await self.session.scalar(
            select(Account.id).where(
                Account.organization_id == organization_id,
                Account.external_number == payload.external_number,
            )
        )
        if exists:
            raise ConflictError("Лицевой счёт с таким номером уже существует")

        account = Account(organization_id=organization_id, **payload.model_dump())
        self.session.add(account)
        await self.session.flush()
        return account

    # ------------------------------------------------------------------
    # Расчётные периоды
    # ------------------------------------------------------------------

    async def create_period(
        self, organization_id: uuid.UUID, payload: BillingPeriodIn
    ) -> BillingPeriod:
        exists = await self.session.scalar(
            select(BillingPeriod.id).where(
                BillingPeriod.organization_id == organization_id,
                BillingPeriod.year == payload.year,
                BillingPeriod.month == payload.month,
            )
        )
        if exists:
            raise ConflictError("Период за этот месяц уже создан")

        period = BillingPeriod(organization_id=organization_id, **payload.model_dump())
        self.session.add(period)
        await self.session.flush()
        return period

    async def list_periods(self, organization_id: uuid.UUID) -> list[BillingPeriod]:
        result = await self.session.scalars(
            select(BillingPeriod)
            .where(BillingPeriod.organization_id == organization_id)
            .order_by(BillingPeriod.year.desc(), BillingPeriod.month.desc())
        )
        return list(result.all())

    async def get_period(self, period_id: uuid.UUID) -> BillingPeriod:
        period = await self.session.get(BillingPeriod, period_id)
        if period is None:
            raise NotFoundError("Расчётный период не найден")
        return period

    # ------------------------------------------------------------------
    # Импорт начислений
    # ------------------------------------------------------------------

    async def import_charges(
        self, organization_id: uuid.UUID, payload: ChargeImportIn
    ) -> ChargeImportOut:
        """Загружает начисления в черновик периода.

        Неизвестные виды услуг создаются автоматически — иначе организации
        пришлось бы вручную заводить справочник перед первым импортом.
        """
        period = await self.get_period(payload.period_id)
        if period.organization_id != organization_id:
            raise PermissionDeniedError("Период принадлежит другой организации")
        if period.status != BillingPeriodStatus.DRAFT:
            raise ConflictError("Начисления можно загружать только в черновик периода")

        accounts = {
            a.external_number: a
            for a in await self.session.scalars(
                select(Account).where(Account.organization_id == organization_id)
            )
        }
        services = {s.name.lower(): s for s in await self.list_service_types(organization_id)}

        # Перезагрузка периода заменяет ранее импортированные начисления
        await self.session.execute(
            Charge.__table__.delete().where(Charge.billing_period_id == period.id)
        )

        imported = 0
        total = 0
        unknown_accounts: set[str] = set()
        created_services: list[str] = []

        for row in payload.charges:
            account = accounts.get(row.account_number.strip())
            if account is None:
                unknown_accounts.add(row.account_number)
                continue

            key = row.service_name.strip().lower()
            service = services.get(key)
            if service is None:
                service = ServiceType(
                    organization_id=organization_id, name=row.service_name.strip()
                )
                self.session.add(service)
                await self.session.flush()
                services[key] = service
                created_services.append(service.name)

            self.session.add(
                Charge(
                    account_id=account.id,
                    billing_period_id=period.id,
                    service_type_id=service.id,
                    amount=row.amount,
                    volume=row.volume,
                    tariff=row.tariff,
                )
            )
            imported += 1
            total += row.amount

        await self.session.flush()
        log.info("billing.charges_imported", period=str(period.id), count=imported)
        return ChargeImportOut(
            imported=imported,
            skipped_unknown_account=sorted(unknown_accounts),
            created_service_types=created_services,
            total_amount=total,
        )

    # ------------------------------------------------------------------
    # Публикация периода
    # ------------------------------------------------------------------

    async def publish_period(
        self, organization_id: uuid.UUID, period_id: uuid.UUID
    ) -> tuple[int, int]:
        """Собирает квитанции из начислений и открывает их жильцам."""
        period = await self.get_period(period_id)
        if period.organization_id != organization_id:
            raise PermissionDeniedError("Период принадлежит другой организации")
        if period.status != BillingPeriodStatus.DRAFT:
            raise ConflictError("Период уже опубликован")

        rows = await self.session.execute(
            select(Charge.account_id, func.sum(Charge.amount))
            .where(Charge.billing_period_id == period_id)
            .group_by(Charge.account_id)
        )
        grouped = rows.all()
        if not grouped:
            raise ValidationError("В периоде нет начислений — публиковать нечего")

        created = 0
        total = 0
        for account_id, amount in grouped:
            invoice = Invoice(
                account_id=account_id,
                billing_period_id=period_id,
                total_amount=int(amount),
                due_date=period.due_date,
            )
            self.session.add(invoice)
            await self.session.flush()

            await self.session.execute(
                Charge.__table__.update()
                .where(
                    Charge.billing_period_id == period_id,
                    Charge.account_id == account_id,
                )
                .values(invoice_id=invoice.id)
            )
            created += 1
            total += int(amount)

        period.status = BillingPeriodStatus.PUBLISHED
        period.published_at = datetime.now(UTC)
        await self.session.flush()

        # Ранее пришедшие платежи могли ждать этих начислений
        await self._allocate_pending_payments(organization_id)

        log.info("billing.period_published", period=str(period_id), invoices=created)
        return created, total

    # ------------------------------------------------------------------
    # Квитанции жильца
    # ------------------------------------------------------------------

    async def list_invoices_for_apartments(
        self, apartment_ids: set[uuid.UUID], year: int | None = None
    ) -> list[tuple[Invoice, BillingPeriod, Account]]:
        if not apartment_ids:
            return []

        query = (
            select(Invoice, BillingPeriod, Account)
            .join(Account, Invoice.account_id == Account.id)
            .join(BillingPeriod, Invoice.billing_period_id == BillingPeriod.id)
            .where(Account.apartment_id.in_(apartment_ids))
            .order_by(BillingPeriod.year.desc(), BillingPeriod.month.desc())
        )
        if year is not None:
            query = query.where(BillingPeriod.year == year)

        rows = await self.session.execute(query)
        return [(r[0], r[1], r[2]) for r in rows.all()]

    async def get_invoice(self, invoice_id: uuid.UUID) -> Invoice:
        invoice = await self.session.get(Invoice, invoice_id)
        if invoice is None:
            raise NotFoundError("Квитанция не найдена")
        return invoice

    async def get_invoice_apartment(self, invoice_id: uuid.UUID) -> uuid.UUID:
        apartment_id = await self.session.scalar(
            select(Account.apartment_id)
            .join(Invoice, Invoice.account_id == Account.id)
            .where(Invoice.id == invoice_id)
        )
        if apartment_id is None:
            raise NotFoundError("Квитанция не найдена")
        return apartment_id

    # ------------------------------------------------------------------
    # Заявление жильца об оплате
    # ------------------------------------------------------------------

    async def create_payment_claim(
        self, invoice_id: uuid.UUID, user_id: uuid.UUID, payload: PaymentClaimIn
    ) -> PaymentClaim:
        """Фиксирует «я оплатил». Статус квитанции — ожидание подтверждения."""
        invoice = await self.get_invoice(invoice_id)

        pending = await self.session.scalar(
            select(PaymentClaim.id).where(
                PaymentClaim.invoice_id == invoice_id,
                PaymentClaim.status == PaymentClaimStatus.PENDING,
            )
        )
        if pending:
            raise ConflictError("По этой квитанции уже есть неподтверждённое заявление об оплате")

        claim = PaymentClaim(
            invoice_id=invoice_id,
            user_id=user_id,
            **payload.model_dump(),
        )
        self.session.add(claim)

        if invoice.status in (InvoiceStatus.ISSUED, InvoiceStatus.OVERDUE):
            invoice.status = InvoiceStatus.AWAITING_CONFIRMATION

        await self.session.flush()
        log.info("billing.claim_created", invoice=str(invoice_id))
        return claim

    # ------------------------------------------------------------------
    # Импорт банковского реестра и сверка
    # ------------------------------------------------------------------

    async def import_payment_registry(
        self, organization_id: uuid.UUID, payload: PaymentRegistryImportIn
    ) -> PaymentRegistryImportOut:
        accounts = {
            a.external_number: a
            for a in await self.session.scalars(
                select(Account).where(Account.organization_id == organization_id)
            )
        }
        known_refs = set(
            (
                await self.session.scalars(
                    select(PaymentFact.external_ref).where(
                        PaymentFact.organization_id == organization_id
                    )
                )
            ).all()
        )

        imported = 0
        duplicates = 0
        total = 0
        unrecognized: set[str] = set()
        facts: list[PaymentFact] = []

        for row in payload.payments:
            if row.external_ref in known_refs:
                duplicates += 1
                continue
            known_refs.add(row.external_ref)

            account = accounts.get(row.account_number.strip())
            if account is None:
                unrecognized.add(row.account_number)

            fact = PaymentFact(
                organization_id=organization_id,
                account_id=account.id if account else None,
                raw_account_number=row.account_number,
                amount=row.amount,
                paid_at=row.paid_at,
                external_ref=row.external_ref,
                source=payload.source,
                payer_name=row.payer_name,
                comment=row.comment,
                unallocated_amount=row.amount,
            )
            self.session.add(fact)
            facts.append(fact)
            imported += 1
            total += row.amount

        await self.session.flush()

        matched = 0
        for fact in facts:
            if fact.account_id is not None:
                matched += await self._allocate_fact(fact)

        log.info("billing.registry_imported", count=imported, matched=matched)
        return PaymentRegistryImportOut(
            imported=imported,
            duplicates_skipped=duplicates,
            matched_invoices=matched,
            unrecognized_accounts=sorted(unrecognized),
            total_amount=total,
        )

    async def _allocate_fact(
        self, fact: PaymentFact, performed_by: uuid.UUID | None = None
    ) -> int:
        """Разносит платёж по неоплаченным квитанциям, начиная с самой старой."""
        if fact.account_id is None or fact.unallocated_amount <= 0:
            return 0

        invoices = list(
            (
                await self.session.scalars(
                    select(Invoice)
                    .join(BillingPeriod, Invoice.billing_period_id == BillingPeriod.id)
                    .where(
                        Invoice.account_id == fact.account_id,
                        Invoice.status != InvoiceStatus.PAID,
                    )
                    .order_by(BillingPeriod.year, BillingPeriod.month)
                )
            ).all()
        )

        matched = 0
        for invoice in invoices:
            if fact.unallocated_amount <= 0:
                break
            outstanding = invoice.outstanding
            if outstanding <= 0:
                continue

            applied = min(outstanding, fact.unallocated_amount)
            invoice.paid_amount += applied
            fact.unallocated_amount -= applied
            self._refresh_invoice_status(invoice)

            self.session.add(
                ReconciliationEntry(
                    payment_fact_id=fact.id,
                    invoice_id=invoice.id,
                    action=(
                        ReconciliationAction.MANUAL_MATCHED
                        if performed_by
                        else ReconciliationAction.AUTO_MATCHED
                    ),
                    amount=applied,
                    performed_by=performed_by,
                )
            )
            await self._confirm_claims(invoice, fact)
            matched += 1

        fact.is_matched = fact.unallocated_amount == 0
        await self._recalculate_balance(fact.account_id)
        await self.session.flush()
        return matched

    async def _confirm_claims(self, invoice: Invoice, fact: PaymentFact) -> None:
        """Подтверждает заявления жильца, как только пришёл реальный платёж."""
        claims = await self.session.scalars(
            select(PaymentClaim).where(
                PaymentClaim.invoice_id == invoice.id,
                PaymentClaim.status == PaymentClaimStatus.PENDING,
            )
        )
        for claim in claims:
            claim.status = PaymentClaimStatus.MATCHED
            claim.matched_fact_id = fact.id
            self.session.add(
                ReconciliationEntry(
                    payment_fact_id=fact.id,
                    payment_claim_id=claim.id,
                    invoice_id=invoice.id,
                    action=ReconciliationAction.CLAIM_CONFIRMED,
                    amount=claim.amount,
                )
            )

    @staticmethod
    def _refresh_invoice_status(invoice: Invoice) -> None:
        if invoice.paid_amount >= invoice.total_amount:
            invoice.status = InvoiceStatus.PAID
        elif invoice.paid_amount > 0:
            invoice.status = InvoiceStatus.PARTIALLY_PAID
        elif invoice.due_date and invoice.due_date < date.today():
            invoice.status = InvoiceStatus.OVERDUE
        else:
            invoice.status = InvoiceStatus.ISSUED

    async def _recalculate_balance(self, account_id: uuid.UUID) -> None:
        """Баланс лицевого счёта: переплата минус долг."""
        debt = await self.session.scalar(
            select(func.coalesce(func.sum(Invoice.total_amount - Invoice.paid_amount), 0)).where(
                Invoice.account_id == account_id
            )
        )
        overpay = await self.session.scalar(
            select(func.coalesce(func.sum(PaymentFact.unallocated_amount), 0)).where(
                PaymentFact.account_id == account_id
            )
        )
        account = await self.session.get(Account, account_id)
        if account is not None:
            account.balance = int(overpay or 0) - int(debt or 0)

    async def _allocate_pending_payments(self, organization_id: uuid.UUID) -> None:
        """Разносит переплаты, которые ждали новых начислений."""
        facts = await self.session.scalars(
            select(PaymentFact).where(
                PaymentFact.organization_id == organization_id,
                PaymentFact.is_matched.is_(False),
                PaymentFact.unallocated_amount > 0,
                PaymentFact.account_id.isnot(None),
            )
        )
        for fact in facts:
            await self._allocate_fact(fact)

    # ------------------------------------------------------------------
    # Ручная сверка
    # ------------------------------------------------------------------

    async def list_unmatched_facts(self, organization_id: uuid.UUID) -> list[PaymentFact]:
        """Платежи, которые не удалось разнести автоматически."""
        result = await self.session.scalars(
            select(PaymentFact)
            .where(
                PaymentFact.organization_id == organization_id,
                PaymentFact.is_matched.is_(False),
            )
            .order_by(PaymentFact.paid_at.desc())
        )
        return list(result.all())

    async def manual_match(
        self,
        organization_id: uuid.UUID,
        fact_id: uuid.UUID,
        invoice_id: uuid.UUID,
        amount: int | None,
        performed_by: uuid.UUID,
    ) -> PaymentFact:
        fact = await self.session.get(PaymentFact, fact_id)
        if fact is None or fact.organization_id != organization_id:
            raise NotFoundError("Платёж не найден")

        invoice = await self.get_invoice(invoice_id)
        applied = min(amount or fact.unallocated_amount, fact.unallocated_amount, invoice.outstanding)
        if applied <= 0:
            raise ValidationError("Нечего разносить: платёж исчерпан или квитанция закрыта")

        # Если счёт в реестре не опознали — привязываем платёж к счёту квитанции
        if fact.account_id is None:
            fact.account_id = invoice.account_id

        invoice.paid_amount += applied
        fact.unallocated_amount -= applied
        fact.is_matched = fact.unallocated_amount == 0
        self._refresh_invoice_status(invoice)

        self.session.add(
            ReconciliationEntry(
                payment_fact_id=fact.id,
                invoice_id=invoice.id,
                action=ReconciliationAction.MANUAL_MATCHED,
                amount=applied,
                performed_by=performed_by,
            )
        )
        await self._confirm_claims(invoice, fact)
        await self._recalculate_balance(invoice.account_id)
        await self.session.flush()
        return fact

    # ------------------------------------------------------------------
    # Отчёты
    # ------------------------------------------------------------------

    async def list_debtors(self, organization_id: uuid.UUID, min_debt: int = 1) -> list[dict]:
        rows = await self.session.execute(
            select(
                Apartment.number,
                Building.number,
                Account.external_number,
                func.sum(Invoice.total_amount - Invoice.paid_amount).label("debt"),
                func.count(Invoice.id).label("invoices"),
            )
            .join(Account, Invoice.account_id == Account.id)
            .join(Apartment, Account.apartment_id == Apartment.id)
            .join(Entrance, Apartment.entrance_id == Entrance.id)
            .join(Building, Entrance.building_id == Building.id)
            .join(Complex, Building.complex_id == Complex.id)
            .where(
                Complex.organization_id == organization_id,
                Invoice.status != InvoiceStatus.PAID,
            )
            .group_by(Apartment.number, Building.number, Account.external_number)
            .having(func.sum(Invoice.total_amount - Invoice.paid_amount) >= min_debt)
            .order_by(func.sum(Invoice.total_amount - Invoice.paid_amount).desc())
        )
        return [
            {
                "apartment_number": r[0],
                "building_number": r[1],
                "account_number": r[2],
                "debt": int(r[3]),
                "overdue_invoices": int(r[4]),
            }
            for r in rows.all()
        ]

    async def collection_summary(self, organization_id: uuid.UUID, period_id: uuid.UUID) -> dict:
        """Собираемость за период — главный показатель для организации."""
        row = await self.session.execute(
            select(
                func.count(Invoice.id),
                func.coalesce(func.sum(Invoice.total_amount), 0),
                func.coalesce(func.sum(Invoice.paid_amount), 0),
            ).where(Invoice.billing_period_id == period_id)
        )
        count, charged, collected = row.one()
        return {
            "invoices": int(count),
            "charged": int(charged),
            "collected": int(collected),
            "collection_rate": round(int(collected) / int(charged) * 100, 1) if charged else 0.0,
        }

    @staticmethod
    def ensure_access(organization_id: uuid.UUID, scope: AccessScope) -> None:
        scope.ensure(organization_id)
