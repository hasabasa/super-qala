"""Эндпоинты чата: каналы, сообщения, WebSocket."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from redis.asyncio import Redis
from sqlalchemy import select

from app.core.db import SessionFactory
from app.core.deps import CurrentUser, DbSession, Scope
from app.core.exceptions import PermissionDeniedError
from app.core.redis import get_redis, redis_client
from app.core.security import decode_token
from app.modules.auth.models import User
from app.modules.chat import ws
from app.modules.chat.schemas import (
    AttachmentOut,
    ChannelOut,
    MarkReadIn,
    MessageIn,
    MessageOut,
    MessagePage,
    MuteIn,
)
from app.modules.chat.service import ChatService

router = APIRouter(tags=["chat"])

RedisDep = Annotated[Redis, Depends(get_redis)]


def get_service(session: DbSession) -> ChatService:
    return ChatService(session)


ServiceDep = Annotated[ChatService, Depends(get_service)]


def _message_out(message, author: User) -> MessageOut:
    return MessageOut(
        id=message.id,
        channel_id=message.channel_id,
        author=ChatService.author_out(author),
        text=message.text,
        reply_to_id=message.reply_to_id,
        is_pinned=message.is_pinned,
        is_important=message.is_important,
        is_deleted=message.deleted_at is not None,
        attachments=[AttachmentOut.model_validate(a) for a in message.attachments],
        created_at=message.created_at,
    )


@router.get("/chat/channels", response_model=list[ChannelOut], summary="Мои каналы")
async def list_channels(user: CurrentUser, service: ServiceDep, scope: Scope) -> list[ChannelOut]:
    channels = await service.list_channels(user)
    ids = [c.id for c in channels]
    unread = await service.unread_counts(user.id, ids)
    last = await service.last_messages(ids)

    result: list[ChannelOut] = []
    for channel in channels:
        organization_id = await service.channel_organization(channel)
        is_staff = scope.allows(organization_id)
        pair = last.get(channel.id)
        result.append(
            ChannelOut(
                id=channel.id,
                type=channel.type,
                name=channel.name,
                is_readonly=channel.is_readonly,
                can_write=await service.can_write(user, channel, is_staff),
                unread_count=unread.get(channel.id, 0),
                last_message=_message_out(*pair) if pair else None,
            )
        )
    return result


@router.get(
    "/chat/channels/{channel_id}/messages",
    response_model=MessagePage,
    summary="История сообщений",
)
async def list_messages(
    channel_id: uuid.UUID,
    user: CurrentUser,
    service: ServiceDep,
    scope: Scope,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    cursor: Annotated[str | None, Query()] = None,
) -> MessagePage:
    channel = await service.get_channel(channel_id)
    is_staff = scope.allows(await service.channel_organization(channel))
    if not await service.can_read(user.id, channel, is_staff):
        raise PermissionDeniedError("Нет доступа к этому каналу")

    rows, next_cursor = await service.list_messages(channel_id, limit, cursor)
    return MessagePage(
        items=[_message_out(m, author) for m, author in rows], next_cursor=next_cursor
    )


@router.post(
    "/chat/channels/{channel_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Отправить сообщение",
)
async def send_message(
    channel_id: uuid.UUID,
    payload: MessageIn,
    user: CurrentUser,
    service: ServiceDep,
    scope: Scope,
    redis: RedisDep,
) -> MessageOut:
    channel = await service.get_channel(channel_id)
    organization_id = await service.channel_organization(channel)
    is_staff = scope.allows(organization_id)

    if not await service.can_read(user.id, channel, is_staff):
        raise PermissionDeniedError("Нет доступа к этому каналу")

    if not await service.can_write(user, channel, is_staff):
        raise PermissionDeniedError("В этот канал писать нельзя")
    if payload.is_important and not is_staff:
        raise PermissionDeniedError("Важные объявления публикуют только сотрудники организации")

    message = await service.create_message(channel_id, user, payload)
    out = _message_out(message, user)
    await ws.publish(redis, channel_id, {"event": "message", "data": out.model_dump(mode="json")})
    return out


@router.delete(
    "/chat/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить сообщение",
)
async def delete_message(
    message_id: uuid.UUID,
    user: CurrentUser,
    service: ServiceDep,
    scope: Scope,
    redis: RedisDep,
) -> None:
    from app.modules.chat.models import Message

    message = await service.session.get(Message, message_id)
    if message is None:
        raise PermissionDeniedError("Сообщение не найдено")

    channel = await service.get_channel(message.channel_id)
    is_staff = scope.allows(await service.channel_organization(channel))
    await service.delete_message(message_id, user, is_staff)
    await ws.publish(
        redis, channel.id, {"event": "message_deleted", "data": {"id": str(message_id)}}
    )


@router.post(
    "/chat/channels/{channel_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Отметить канал прочитанным",
)
async def mark_read(
    channel_id: uuid.UUID, payload: MarkReadIn, user: CurrentUser, service: ServiceDep
) -> None:
    await service.mark_read(channel_id, user.id, payload.last_read_at)


@router.post(
    "/chat/channels/{channel_id}/mute",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Ограничить пользователя в канале",
)
async def mute_member(
    channel_id: uuid.UUID, payload: MuteIn, service: ServiceDep, scope: Scope
) -> None:
    channel = await service.get_channel(channel_id)
    organization_id = await service.channel_organization(channel)
    scope.ensure(organization_id)
    await service.mute_member(channel_id, payload.user_id, payload.hours)


@router.websocket("/chat/ws/{channel_id}")
async def chat_websocket(
    websocket: WebSocket, channel_id: uuid.UUID, token: Annotated[str, Query()]
) -> None:
    """Живая лента канала.

    Токен передаётся параметром запроса: браузер не позволяет задать
    заголовок Authorization при открытии WebSocket.
    """
    try:
        payload = decode_token(token, expected_type="access")
        user_id = uuid.UUID(payload["sub"])
    except Exception:  # noqa: BLE001
        await websocket.close(code=4401)
        return

    async with SessionFactory() as session:
        service = ChatService(session)
        try:
            channel = await service.get_channel(channel_id)
        except Exception:  # noqa: BLE001
            await websocket.close(code=4404)
            return
        user = await session.scalar(select(User).where(User.id == user_id))
        organization_id = await service.channel_organization(channel)
        is_staff = any(
            r.organization_id == organization_id or r.role == "platform_admin"
            for r in (user.roles if user else [])
        )
        if not await service.can_read(user_id, channel, is_staff):
            await websocket.close(code=4403)
            return

    await websocket.accept()
    await websocket.send_json(
        {"event": "connected", "data": {"channel_id": str(channel_id), "user_id": str(user_id)}}
    )

    import asyncio

    listener = asyncio.create_task(ws.subscribe(redis_client, channel_id, websocket))
    try:
        while True:
            incoming = await websocket.receive_json()
            if incoming.get("event") == "ping":
                await websocket.send_json({"event": "pong"})
            elif incoming.get("event") == "read":
                async with SessionFactory() as session:
                    await ChatService(session).mark_read(channel_id, user_id, datetime.now(UTC))
                    await session.commit()
    except WebSocketDisconnect:
        pass
    finally:
        listener.cancel()
        await ws.registry.remove(channel_id, websocket)
