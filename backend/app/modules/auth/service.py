"""Бизнес-логика авторизации: SMS-код, выпуск и обновление токенов."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import RateLimitError, UnauthorizedError, ValidationError
from app.core.security import create_token, decode_token, generate_sms_code, hash_token
from app.modules.auth.models import PhoneVerification, RefreshToken, User
from app.modules.auth.schemas import TokenPair
from app.modules.auth.sms import get_sms_provider
from app.shared.phone import normalize_phone

log = structlog.get_logger(__name__)

MAX_CODE_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


class AuthService:
    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        self.session = session
        self.redis = redis

    # ------------------------------------------------------------------
    # Отправка кода
    # ------------------------------------------------------------------

    async def request_code(self, raw_phone: str, ip: str | None) -> tuple[int, int, str | None]:
        """Отправляет код подтверждения. Возвращает (ttl, cooldown, код для отладки)."""
        phone = normalize_phone(raw_phone)

        await self._check_cooldown(phone)
        await self._check_rate_limits(phone, ip)

        code = generate_sms_code()
        verification = PhoneVerification(
            phone=phone,
            code_hash=_hash_code(code),
            expires_at=datetime.now(UTC) + timedelta(seconds=settings.SMS_CODE_TTL_SECONDS),
            ip_address=ip,
        )
        self.session.add(verification)
        await self.session.flush()

        await get_sms_provider().send(phone, f"SmartQala: код подтверждения {code}")
        await self.redis.setex(f"sms:cooldown:{phone}", RESEND_COOLDOWN_SECONDS, "1")

        log.info("auth.code_sent", phone=phone)
        return (
            settings.SMS_CODE_TTL_SECONDS,
            RESEND_COOLDOWN_SECONDS,
            code if settings.is_local else None,
        )

    async def _check_cooldown(self, phone: str) -> None:
        ttl = await self.redis.ttl(f"sms:cooldown:{phone}")
        if ttl and ttl > 0:
            raise RateLimitError(
                f"Повторная отправка возможна через {ttl} секунд", retry_after=ttl
            )

    async def _check_rate_limits(self, phone: str, ip: str | None) -> None:
        limits = [(f"sms:limit:phone:{phone}", settings.SMS_RATE_LIMIT_PER_PHONE_HOUR)]
        if ip:
            limits.append((f"sms:limit:ip:{ip}", settings.SMS_RATE_LIMIT_PER_IP_HOUR))

        for key, limit in limits:
            used = await self.redis.incr(key)
            if used == 1:
                await self.redis.expire(key, 3600)
            if used > limit:
                raise RateLimitError("Слишком много запросов кода. Попробуйте через час")

    # ------------------------------------------------------------------
    # Проверка кода и вход
    # ------------------------------------------------------------------

    async def verify_code(
        self, raw_phone: str, code: str, user_agent: str | None
    ) -> tuple[TokenPair, bool]:
        phone = normalize_phone(raw_phone)
        now = datetime.now(UTC)

        verification = await self.session.scalar(
            select(PhoneVerification)
            .where(
                PhoneVerification.phone == phone,
                PhoneVerification.confirmed_at.is_(None),
                PhoneVerification.expires_at > now,
            )
            .order_by(PhoneVerification.created_at.desc())
            .limit(1)
        )

        if verification is None:
            raise ValidationError("Код не найден или истёк. Запросите новый")

        if verification.attempts >= MAX_CODE_ATTEMPTS:
            raise RateLimitError("Превышено число попыток. Запросите новый код")

        if verification.code_hash != _hash_code(code):
            verification.attempts += 1
            await self.session.flush()
            remaining = MAX_CODE_ATTEMPTS - verification.attempts
            raise ValidationError("Неверный код", attempts_left=max(remaining, 0))

        verification.confirmed_at = now

        user = await self.session.scalar(select(User).where(User.phone == phone))
        is_new_user = user is None

        if user is None:
            user = User(phone=phone)
            self.session.add(user)
            await self.session.flush()
        elif not user.is_active:
            raise UnauthorizedError("Пользователь заблокирован")

        user.last_seen_at = now
        # Профиль считается незаполненным, пока не указано имя
        is_new_user = is_new_user or not user.first_name

        tokens = await self._issue_tokens(user, user_agent)
        log.info("auth.login", user_id=str(user.id), is_new=is_new_user)
        return tokens, is_new_user

    async def _issue_tokens(self, user: User, user_agent: str | None) -> TokenPair:
        access = create_token(str(user.id), "access")
        refresh = create_token(str(user.id), "refresh")

        self.session.add(
            RefreshToken(
                user_id=user.id,
                token_hash=hash_token(refresh),
                expires_at=datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS),
                user_agent=(user_agent or "")[:300] or None,
            )
        )
        await self.session.flush()
        return TokenPair(access_token=access, refresh_token=refresh)

    # ------------------------------------------------------------------
    # Обновление и выход
    # ------------------------------------------------------------------

    async def refresh(self, raw_token: str, user_agent: str | None) -> TokenPair:
        payload = decode_token(raw_token, expected_type="refresh")
        stored = await self.session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token))
        )

        if stored is None or not stored.is_valid:
            raise UnauthorizedError("Токен недействителен. Войдите заново")

        # Ротация: использованный токен сразу отзывается
        stored.revoked_at = datetime.now(UTC)

        user = await self.session.scalar(select(User).where(User.id == uuid.UUID(payload["sub"])))
        if user is None or not user.is_active:
            raise UnauthorizedError("Пользователь не найден или заблокирован")

        return await self._issue_tokens(user, user_agent)

    async def logout(self, user_id: uuid.UUID, raw_token: str | None = None) -> None:
        """Без токена отзывает все сессии пользователя, с токеном — только текущую."""
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        if raw_token:
            stmt = stmt.where(RefreshToken.token_hash == hash_token(raw_token))
        await self.session.execute(stmt)
