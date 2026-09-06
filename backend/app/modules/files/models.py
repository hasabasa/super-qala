"""Учёт загруженных файлов.

Запись нужна, чтобы знать автора, назначение и размер: без неё
хранилище со временем превращается в свалку без возможности уборки.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin


class StoredFile(Base, TimestampMixin):
    __tablename__ = "stored_files"
    __table_args__ = (Index("ix_stored_files_owner", "uploaded_by"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(300), unique=True, nullable=False)
    url: Mapped[str] = mapped_column(String(600), nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String(600))
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    original_name: Mapped[str | None] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    is_attached: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="Привязан ли файл к объекту"
    )
