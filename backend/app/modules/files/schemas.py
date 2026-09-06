"""Схемы загрузки файлов."""

import uuid

from pydantic import BaseModel, ConfigDict


class UploadedFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    thumbnail_url: str | None
    content_type: str
    size_bytes: int
    width: int | None
    height: int | None
