"""Общие зависимости FastAPI: текущий пользователь, роли, доступ к организации."""

import uuid
from collections.abc import Callable, Coroutine
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


async def get_organization_scope(user: CurrentUser) -> set[uuid.UUID]:
    """Организации, данные которых пользователь вправе видеть.

    Накладывается на запросы фильтром — администратор ОСИ физически
    не может получить данные чужого ЖК.
    """
    return {r.organization_id for r in user.roles if r.organization_id is not None}


OrganizationScope = Annotated[set[uuid.UUID], Depends(get_organization_scope)]
