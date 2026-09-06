"""Выпуск и проверка JWT-токенов."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt

from app.core.config import settings
from app.core.exceptions import UnauthorizedError

ALGORITHM = "HS256"
TokenType = Literal["access", "refresh"]


def create_token(
    subject: str,
    token_type: TokenType,
    extra: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    ttl = (
        timedelta(minutes=settings.ACCESS_TOKEN_TTL_MINUTES)
        if token_type == "access"
        else timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS)
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + ttl,
        "jti": secrets.token_urlsafe(16),
        **(extra or {}),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str, expected_type: TokenType = "access") -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[ALGORITHM]
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Срок действия токена истёк") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Некорректный токен") from exc

    if payload.get("type") != expected_type:
        raise UnauthorizedError("Некорректный тип токена")
    return payload


def generate_sms_code() -> str:
    """Числовой код для SMS-верификации."""
    upper = 10**settings.SMS_CODE_LENGTH
    return str(secrets.randbelow(upper)).zfill(settings.SMS_CODE_LENGTH)


def hash_token(raw: str) -> str:
    """Refresh-токены хранятся в БД только в виде хеша."""
    import hashlib

    return hashlib.sha256(raw.encode()).hexdigest()
