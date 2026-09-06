"""Общие зависимости FastAPI: текущий пользователь, роли, доступ к организации."""

import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.exceptions import PermissionDeniedError, UnauthorizedError
from app.core.security import decode_token
from app.modules.auth.models import User
from app.shared.enums import UserRoleType

DbSession = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    session: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError()

    payload = decode_token(authorization.split(" ", 1)[1], expected_type="access")
    user = await session.scalar(select(User).where(User.id == uuid.UUID(payload["sub"])))

    if user is None or not user.is_active:
        raise UnauthorizedError("Пользователь не найден или заблокирован")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(
    *allowed: UserRoleType,
) -> Callable[[User], Coroutine[Any, Any, User]]:
    """Ограничивает доступ к эндпоинту набором ролей."""

    async def checker(user: CurrentUser) -> User:
        user_roles = {r.role for r in user.roles}
        if UserRoleType.PLATFORM_ADMIN in user_roles:
            return user
        if not user_roles & {r.value for r in allowed}:
            raise PermissionDeniedError()
        return user

    return checker


@dataclass(frozen=True)
class AccessScope:
    """Границы доступа пользователя к данным организаций.

    Администратор ОСИ видит только свои организации; администратор
    платформы — все. Проверка идёт через allows(), а не сравнением
    множеств, иначе роль без организации (platform_admin) отсекает сама себя.
    """

    organization_ids: frozenset[uuid.UUID]
    is_platform_admin: bool

    def allows(self, organization_id: uuid.UUID) -> bool:
        return self.is_platform_admin or organization_id in self.organization_ids

    def ensure(self, organization_id: uuid.UUID) -> None:
        if not self.allows(organization_id):
            raise PermissionDeniedError("Нет доступа к этой организации")


async def get_access_scope(user: CurrentUser) -> AccessScope:
    roles = user.roles
    return AccessScope(
        organization_ids=frozenset(
            r.organization_id for r in roles if r.organization_id is not None
        ),
        is_platform_admin=any(r.role == UserRoleType.PLATFORM_ADMIN for r in roles),
    )


Scope = Annotated[AccessScope, Depends(get_access_scope)]
