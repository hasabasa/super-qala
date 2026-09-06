"""Приём и обработка загружаемых файлов.

Изображения уменьшаются на сервере: аудитория сидит на 3G, и отдавать
восьмимегапиксельный снимок протекающего крана нельзя.
"""

import asyncio
import io
import uuid
from datetime import UTC, datetime

import structlog
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.exceptions import NotFoundError, ValidationError
from app.modules.files.models import StoredFile

log = structlog.get_logger(__name__)

IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}
DOCUMENT_TYPES = {"application/pdf"}

# Ограничения по назначению: чек — маленький, документ ОСИ может быть крупным
LIMITS_MB: dict[str, int] = {
    "avatar": 5,
    "request": 10,
    "receipt": 10,
    "meter": 10,
    "listing": 10,
    "message": 15,
    "document": 25,
}
ALLOWED_TYPES: dict[str, set[str]] = {
    "avatar": IMAGE_TYPES,
    "request": IMAGE_TYPES,
    "receipt": IMAGE_TYPES | DOCUMENT_TYPES,
    "meter": IMAGE_TYPES,
    "listing": IMAGE_TYPES,
    "message": IMAGE_TYPES,
    "document": IMAGE_TYPES | DOCUMENT_TYPES,
}

MAX_SIDE = 1920
THUMBNAIL_SIDE = 400
JPEG_QUALITY = 82


def _process_image(raw: bytes) -> tuple[bytes, bytes, int, int]:
    """Приводит изображение к разумному размеру и делает миниатюру."""
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError("Файл не является корректным изображением") from exc

    # Разворачиваем по EXIF, иначе фото с телефона окажется боком
    try:
        from PIL import ImageOps

        image = ImageOps.exif_transpose(image)
    except Exception:  # noqa: BLE001
        pass

    if image.mode in ("RGBA", "P", "LA"):
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[-1] if image.mode != "P" else None)
        image = background
    elif image.mode != "RGB":
        image = image.convert("RGB")

    image.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    width, height = image.size

    main = io.BytesIO()
    image.save(main, format="JPEG", quality=JPEG_QUALITY, optimize=True)

    preview = image.copy()
    preview.thumbnail((THUMBNAIL_SIDE, THUMBNAIL_SIDE), Image.Resampling.LANCZOS)
    thumb = io.BytesIO()
    preview.save(thumb, format="JPEG", quality=75, optimize=True)

    return main.getvalue(), thumb.getvalue(), width, height


class FilesService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upload(
        self,
        raw: bytes,
        content_type: str,
        original_name: str | None,
        purpose: str,
        user_id: uuid.UUID,
    ) -> StoredFile:
        allowed = ALLOWED_TYPES.get(purpose)
        if allowed is None:
            raise ValidationError(f"Неизвестное назначение файла: {purpose}")
        if content_type not in allowed:
            raise ValidationError(
                "Недопустимый тип файла", allowed=sorted(allowed), received=content_type
            )

        limit = LIMITS_MB[purpose] * 1024 * 1024
        if len(raw) > limit:
            raise ValidationError(
                f"Файл больше {LIMITS_MB[purpose]} МБ", size_bytes=len(raw), limit_bytes=limit
            )
        if not raw:
            raise ValidationError("Пустой файл")

        prefix = f"{purpose}/{datetime.now(UTC):%Y/%m}/{uuid.uuid4().hex}"
        thumbnail_url: str | None = None
        width: int | None = None
        height: int | None = None

        if content_type in IMAGE_TYPES:
            main, thumb, width, height = await asyncio.to_thread(_process_image, raw)
            key = f"{prefix}.jpg"
            url = await storage.put_object(key, main, "image/jpeg")
            thumbnail_url = await storage.put_object(f"{prefix}_thumb.jpg", thumb, "image/jpeg")
            stored_type = "image/jpeg"
            size = len(main)
        else:
            key = f"{prefix}.pdf"
            url = await storage.put_object(key, raw, content_type)
            stored_type = content_type
            size = len(raw)

        record = StoredFile(
            key=key,
            url=url,
            thumbnail_url=thumbnail_url,
            purpose=purpose,
            content_type=stored_type,
            original_name=(original_name or "")[:255] or None,
            size_bytes=size,
            width=width,
            height=height,
            uploaded_by=user_id,
        )
        self.session.add(record)
        await self.session.flush()
        log.info("files.uploaded", purpose=purpose, size=size, key=key)
        return record

    async def get_by_url(self, url: str) -> StoredFile:
        record = await self.session.scalar(select(StoredFile).where(StoredFile.url == url))
        if record is None:
            raise NotFoundError("Файл не найден")
        return record

    async def mark_attached(self, urls: list[str]) -> None:
        """Помечает файлы использованными, чтобы уборщик их не удалил."""
        if not urls:
            return
        for record in await self.session.scalars(
            select(StoredFile).where(StoredFile.url.in_(urls))
        ):
            record.is_attached = True
        await self.session.flush()

    async def cleanup_orphans(self, older_than_hours: int = 24) -> int:
        """Удаляет файлы, загруженные, но так и не привязанные к объекту."""
        from datetime import timedelta

        threshold = datetime.now(UTC) - timedelta(hours=older_than_hours)
        orphans = list(
            (
                await self.session.scalars(
                    select(StoredFile).where(
                        StoredFile.is_attached.is_(False), StoredFile.created_at < threshold
                    )
                )
            ).all()
        )
        for record in orphans:
            await storage.delete_object(record.key)
            if record.thumbnail_url:
                await storage.delete_object(record.key.replace(".jpg", "_thumb.jpg"))
            await self.session.delete(record)

        await self.session.flush()
        if orphans:
            log.info("files.orphans_removed", count=len(orphans))
        return len(orphans)
