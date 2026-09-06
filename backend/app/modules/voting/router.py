"""Эндпоинты собраний собственников."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.core.deps import CurrentUser, DbSession, Scope
from app.core.exceptions import PermissionDeniedError
from app.modules.chat.service import ChatService
from app.modules.voting.schemas import (
    BallotOut,
    MeetingIn,
    MeetingListOut,
    MeetingOut,
    ResultsOut,
    VoteIn,
)
from app.modules.voting.service import VotingService

router = APIRouter(tags=["voting"])


def get_service(session: DbSession) -> VotingService:
    return VotingService(session)


ServiceDep = Annotated[VotingService, Depends(get_service)]


@router.post(
    "/meetings",
    response_model=MeetingOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать собрание",
)
async def create_meeting(
    payload: MeetingIn, user: CurrentUser, service: ServiceDep, scope: Scope
) -> MeetingOut:
    scope.ensure(await service.organization_of(payload.complex_id))
    return MeetingOut.model_validate(await service.create(payload, user.id))


@router.post("/meetings/{meeting_id}/start", response_model=MeetingOut, summary="Запустить")
async def start_meeting(
    meeting_id: uuid.UUID, service: ServiceDep, scope: Scope
) -> MeetingOut:
    meeting = await service.get(meeting_id)
    scope.ensure(await service.organization_of(meeting.complex_id))
    return MeetingOut.model_validate(await service.start(meeting_id))


@router.post("/meetings/{meeting_id}/finish", response_model=MeetingOut, summary="Завершить")
async def finish_meeting(
    meeting_id: uuid.UUID, service: ServiceDep, scope: Scope
) -> MeetingOut:
    meeting = await service.get(meeting_id)
    scope.ensure(await service.organization_of(meeting.complex_id))
    return MeetingOut.model_validate(await service.finish(meeting_id))


@router.get("/meetings", response_model=list[MeetingListOut], summary="Собрания моего ЖК")
async def list_meetings(
    user: CurrentUser, service: ServiceDep, session: DbSession
) -> list[MeetingListOut]:
    complexes, _, _ = await ChatService(session)._user_scope(user.id)  # noqa: SLF001
    meetings = await service.list_for_complexes(complexes)
    return [
        MeetingListOut(
            id=m.id,
            title=m.title,
            type=m.type,
            status=m.status,
            starts_at=m.starts_at,
            ends_at=m.ends_at,
            has_voted=await service.has_voted(m.id, user.id),
            questions_count=len(m.questions),
        )
        for m in meetings
    ]


@router.get("/meetings/{meeting_id}", response_model=MeetingOut, summary="Повестка собрания")
async def get_meeting(
    meeting_id: uuid.UUID, _: CurrentUser, service: ServiceDep
) -> MeetingOut:
    return MeetingOut.model_validate(await service.get(meeting_id))


@router.post(
    "/meetings/{meeting_id}/vote",
    response_model=BallotOut,
    status_code=status.HTTP_201_CREATED,
    summary="Проголосовать",
)
async def vote(
    meeting_id: uuid.UUID,
    payload: VoteIn,
    request: Request,
    user: CurrentUser,
    service: ServiceDep,
) -> BallotOut:
    ip = request.client.host if request.client else None
    ballot = await service.vote(meeting_id, user.id, payload, ip)
    return BallotOut(
        id=ballot.id,
        apartment_id=ballot.apartment_id,
        weight=ballot.weight,
        submitted_at=ballot.submitted_at,
    )


@router.get(
    "/meetings/{meeting_id}/results",
    response_model=ResultsOut,
    summary="Результаты и кворум",
)
async def results(
    meeting_id: uuid.UUID, _: CurrentUser, service: ServiceDep
) -> ResultsOut:
    return ResultsOut(**await service.results(meeting_id))
