"""Клиент Redis: кэш, pub/sub для чата, брокер фоновых задач."""

from redis.asyncio import Redis, from_url

from app.core.config import settings

redis_client: Redis = from_url(
    str(settings.REDIS_URL),
    encoding="utf-8",
    decode_responses=True,
)


async def get_redis() -> Redis:
    return redis_client
