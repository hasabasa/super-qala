"""Эндпоинты авторизации."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status
from redis.asyncio import Redis

from app.core.deps import CurrentUser, DbSession
from app.core.redis import get_redis
from app.modules.auth.schemas import (
    RefreshIn,
    RequestCodeIn,
    RequestCodeOut,
    TokenPair,
    UserOut,
    UserUpdateIn,
    VerifyCodeIn,
    VerifyCodeOut,
)
from app.modules.auth.service import AuthService

router = APIRouter(tags=["auth"])

RedisDep = Annotated[Redis, Depends(get_redis)]


def get_auth_service(session: DbSession, redis: RedisDep) -> AuthService:
    return AuthService(session, redis)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


@router.post("/auth/request-code", response_model=RequestCodeOut, summary="Запросить код")
async def request_code(
    payload: RequestCodeIn, request: Request, service: AuthServiceDep
) -> RequestCodeOut:
    ip = request.client.host if request.client else None
    ttl, cooldown, debug_code = await service.request_code(payload.phone, ip)
    return RequestCodeOut(expires_in=ttl, retry_after=cooldown, debug_code=debug_code)


@router.post("/auth/verify-code", response_model=VerifyCodeOut, summary="Подтвердить код и войти")
async def verify_code(
    payload: VerifyCodeIn,
    service: AuthServiceDep,
    user_agent: Annotated[str | None, Header()] = None,
) -> VerifyCodeOut:
    tokens, is_new = await service.verify_code(payload.phone, payload.code, user_agent)
    return VerifyCodeOut(**tokens.model_dump(), is_new_user=is_new)


@router.post("/auth/refresh", response_model=TokenPair, summary="Обновить токены")
async def refresh(
    payload: RefreshIn,
    service: AuthServiceDep,
    user_agent: Annotated[str | None, Header()] = None,
) -> TokenPair:
    return await service.refresh(payload.refresh_token, user_agent)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Выйти")
async def logout(user: CurrentUser, service: AuthServiceDep) -> None:
    await service.logout(user.id)


@router.get("/users/me", response_model=UserOut, summary="Текущий пользователь")
async def get_me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("/users/me", response_model=UserOut, summary="Обновить профиль")
async def update_me(payload: UserUpdateIn, user: CurrentUser, session: DbSession) -> UserOut:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await session.flush()
    return UserOut.model_validate(user)
