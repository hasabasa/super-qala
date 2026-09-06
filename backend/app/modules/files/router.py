"""Загрузка файлов."""

from typing import Annotated

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status

from app.core import storage
from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.modules.files.schemas import UploadedFileOut
from app.modules.files.service import LIMITS_MB, FilesService

router = APIRouter(tags=["files"])


def get_service(session: DbSession) -> FilesService:
    return FilesService(session)


ServiceDep = Annotated[FilesService, Depends(get_service)]


@router.post(
    "/files",
    response_model=UploadedFileOut,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить файл",
    description=(
        "Изображения уменьшаются до 1920 px и переводятся в JPEG, "
        "дополнительно создаётся миниатюра 400 px. "
        "Назначение определяет допустимые типы и предельный размер."
    ),
)
async def upload_file(
    user: CurrentUser,
    service: ServiceDep,
    file: Annotated[UploadFile, File()],
    purpose: Annotated[str, Form()] = "request",
) -> UploadedFileOut:
    raw = await file.read()
    record = await service.upload(
        raw=raw,
        content_type=file.content_type or "application/octet-stream",
        original_name=file.filename,
        purpose=purpose,
        user_id=user.id,
    )
    return UploadedFileOut.model_validate(record)


@router.get("/files/limits", summary="Ограничения по назначениям")
async def limits(_: CurrentUser) -> dict[str, int]:
    return dict(LIMITS_MB)


@router.get(
    "/files/{file_id}/download",
    summary="Временная ссылка на непубличный файл",
    description=(
        "Чеки и финансовые документы не отдаются публично: они содержат "
        "персональные и платёжные данные. Эндпоинт выдаёт ссылку с ограниченным "
        "сроком действия."
    ),
)
async def download_link(
    file_id: uuid.UUID,
    user: CurrentUser,
    service: ServiceDep,
    expires_in: Annotated[int, Query(ge=60, le=86400)] = 3600,
) -> dict[str, str | int]:
    from app.modules.files.models import StoredFile

    record = await service.session.get(StoredFile, file_id)
    if record is None:
        raise NotFoundError("Файл не найден")
    if record.uploaded_by != user.id:
        raise PermissionDeniedError("Нет доступа к этому файлу")

    if storage.is_public(record.key):
        return {"url": record.url, "expires_in": 0}
    return {"url": await storage.presigned_url(record.key, expires_in), "expires_in": expires_in}
