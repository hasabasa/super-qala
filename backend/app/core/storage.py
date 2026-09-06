"""Файловое хранилище, совместимое с S3.

Локально работает MinIO из docker compose, в бою — любое S3-совместимое
хранилище на территории Казахстана.
"""

import asyncio
from functools import lru_cache
from typing import Any

import boto3
import structlog
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import settings

log = structlog.get_logger(__name__)


@lru_cache
def get_client(public: bool = False) -> Any:
    """Клиент хранилища.

    public=True возвращает клиента, настроенного на внешний адрес: только
    он годится для подписи временных ссылок, иначе в них попадёт имя
    контейнера, недоступное снаружи.
    """
    endpoint = settings.S3_ENDPOINT_URL
    if public:
        endpoint = settings.S3_PUBLIC_ENDPOINT or settings.S3_ENDPOINT_URL

    return boto3.client(
        "s3",
        endpoint_url=endpoint or None,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
        region_name="us-east-1",
    )


# Публично читаемые назначения: изображения показываются в ленте, чате
# и заявках, и гонять их через API нерационально. Ключи содержат uuid4,
# перебрать их нельзя.
#
# Чеки и финансовые документы под эту политику НЕ попадают: они содержат
# персональные и платёжные данные и отдаются только по временной ссылке
# через /files/{id}/download.
PUBLIC_PREFIXES = ("avatar/", "listing/", "message/", "request/", "meter/")


def _public_read_policy() -> str:
    import json

    statements = [
        {
            "Sid": f"PublicRead{prefix.strip('/').capitalize()}",
            "Effect": "Allow",
            "Principal": {"AWS": ["*"]},
            "Action": ["s3:GetObject"],
            "Resource": [f"arn:aws:s3:::{settings.S3_BUCKET}/{prefix}*"],
        }
        for prefix in PUBLIC_PREFIXES
    ]
    return json.dumps({"Version": "2012-10-17", "Statement": statements})


def _ensure_bucket_sync() -> None:
    client = get_client()
    try:
        client.head_bucket(Bucket=settings.S3_BUCKET)
    except ClientError:
        client.create_bucket(Bucket=settings.S3_BUCKET)
        log.info("storage.bucket_created", bucket=settings.S3_BUCKET)

    client.put_bucket_policy(Bucket=settings.S3_BUCKET, Policy=_public_read_policy())


async def ensure_bucket() -> None:
    """Создаёт бакет при старте приложения, если его ещё нет."""
    try:
        await asyncio.to_thread(_ensure_bucket_sync)
    except Exception as exc:  # noqa: BLE001 — недоступность хранилища не должна ронять API
        log.warning("storage.unavailable", error=str(exc))


def _put_sync(key: str, data: bytes, content_type: str) -> None:
    get_client().put_object(
        Bucket=settings.S3_BUCKET,
        Key=key,
        Body=data,
        ContentType=content_type,
        CacheControl="public, max-age=31536000",
    )


async def put_object(key: str, data: bytes, content_type: str) -> str:
    await asyncio.to_thread(_put_sync, key, data, content_type)
    return public_url(key)


def _delete_sync(key: str) -> None:
    get_client().delete_object(Bucket=settings.S3_BUCKET, Key=key)


async def delete_object(key: str) -> None:
    await asyncio.to_thread(_delete_sync, key)


def public_url(key: str) -> str:
    base = settings.S3_PUBLIC_URL.rstrip("/")
    return f"{base}/{key}" if base else key


def is_public(key: str) -> bool:
    return key.startswith(PUBLIC_PREFIXES)


def _presign_sync(key: str, expires_in: int) -> str:
    return get_client(public=True).generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_BUCKET, "Key": key},
        ExpiresIn=expires_in,
    )


async def presigned_url(key: str, expires_in: int = 3600) -> str:
    """Временная ссылка для файлов, которые нельзя отдавать публично."""
    return await asyncio.to_thread(_presign_sync, key, expires_in)
