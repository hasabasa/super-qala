"""Раздача сообщений через WebSocket.

Соединения живут в памяти процесса, а рассылка идёт через Redis pub/sub.
При одном процессе это избыточно, но позволяет добавить второй инстанс
без переписывания: подписчик получает события и от соседних процессов.
"""

import asyncio
import json
import uuid
from collections import defaultdict
from typing import Any

import structlog
from fastapi import WebSocket
from redis.asyncio import Redis

log = structlog.get_logger(__name__)

CHANNEL_PREFIX = "chat:channel:"


class ConnectionRegistry:
    """Открытые соединения текущего процесса, сгруппированные по каналам."""

    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def add(self, channel_id: uuid.UUID, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections[channel_id].add(websocket)

    async def remove(self, channel_id: uuid.UUID, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections[channel_id].discard(websocket)
            if not self._connections[channel_id]:
                self._connections.pop(channel_id, None)

    async def deliver(self, channel_id: uuid.UUID, payload: dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._connections.get(channel_id, ()))

        for websocket in targets:
            try:
                await websocket.send_json(payload)
            except Exception:  # noqa: BLE001 — разорванное соединение не должно ломать рассылку
                await self.remove(channel_id, websocket)

    def channel_count(self) -> int:
        return len(self._connections)


registry = ConnectionRegistry()


async def publish(redis: Redis, channel_id: uuid.UUID, payload: dict[str, Any]) -> None:
    """Отправляет событие всем процессам, включая текущий."""
    await redis.publish(f"{CHANNEL_PREFIX}{channel_id}", json.dumps(payload, default=str))


async def subscribe(redis: Redis, channel_id: uuid.UUID, websocket: WebSocket) -> None:
    """Держит соединение и пересылает в него события канала."""
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"{CHANNEL_PREFIX}{channel_id}")
    await registry.add(channel_id, websocket)

    try:
        async for event in pubsub.listen():
            if event.get("type") != "message":
                continue
            try:
                await websocket.send_json(json.loads(event["data"]))
            except Exception:  # noqa: BLE001
                break
    finally:
        await registry.remove(channel_id, websocket)
        await pubsub.unsubscribe(f"{CHANNEL_PREFIX}{channel_id}")
        await pubsub.aclose()
