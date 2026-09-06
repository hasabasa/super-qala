"""Собрания собственников.

Кворум и результаты считаются по площади квартир: голос владельца
120 м² весит вдвое против владельца 60 м². Один бюллетень от квартиры,
голосует подтверждённый собственник.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from app.modules.properties.models import Apartment, Building, Complex, Entrance
from app.modules.residents.models import ApartmentResident
from app.modules.voting.models import (
    Ballot,
    BallotAnswer,
    Meeting,
    MeetingQuestion,
    MeetingResult,
)
from app.modules.voting.schemas import MeetingIn, VoteIn
from app.shared.enums import (
    MajorityType,
    MeetingStatus,
    ResidentRelation,
    ResidentStatus,
)

log = structlog.get_logger(__name__)

# Квартира без указанной площади получает вес по умолчанию, иначе
# её собственник не смог бы проголосовать вовсе.
FALLBACK_AREA = Decimal("1")

MAJORITY_THRESHOLD: dict[str, Decimal] = {
    MajorityType.SIMPLE: Decimal("50"),
    MajorityType.QUALIFIED: Decimal("66.67"),
    MajorityType.UNANIMOUS: Decimal("100"),
}


class VotingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Создание и жизненный цикл
    # ------------------------------------------------------------------

    async def create(self, payload: MeetingIn, author_id: uuid.UUID) -> Meeting:
        if payload.ends_at <= payload.starts_at:
            raise ValidationError("Окончание собрания должно быть позже начала")

        meeting = Meeting(
            complex_id=payload.complex_id,
            title=payload.title,
            description=payload.description,
            type=payload.type,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
            quorum_percent=payload.quorum_percent,
            created_by=author_id,
        )
        self.session.add(meeting)
        await self.session.flush()

        for index, question in enumerate(payload.questions):
            self.session.add(
                MeetingQuestion(
                    meeting_id=meeting.id,
                    order_num=index,
                    text=question.text,
                    options=question.options,
                    majority_type=question.majority_type,
                )
            )
        await self.session.flush()
        await self.session.refresh(meeting)
        return meeting

    async def get(self, meeting_id: uuid.UUID) -> Meeting:
        meeting = await self.session.get(Meeting, meeting_id)
        if meeting is None:
            raise NotFoundError("Собрание не найдено")
        return meeting

    async def start(self, meeting_id: uuid.UUID) -> Meeting:
        """Запуск фиксирует общую площадь: она не должна меняться по ходу."""
        meeting = await self.get(meeting_id)
        if meeting.status != MeetingStatus.DRAFT:
            raise ConflictError("Собрание уже запущено или завершено")

        meeting.total_area = await self._complex_area(meeting.complex_id)
        meeting.status = MeetingStatus.ACTIVE
        await self.session.flush()
        log.info("voting.started", meeting=str(meeting_id), area=str(meeting.total_area))
        return meeting

    async def finish(self, meeting_id: uuid.UUID) -> Meeting:
        meeting = await self.get(meeting_id)
        if meeting.status != MeetingStatus.ACTIVE:
            raise ConflictError("Завершить можно только идущее собрание")

        results = await self.results(meeting_id)
        await self.session.execute(
            MeetingResult.__table__.delete().where(MeetingResult.meeting_id == meeting_id)
        )
        for question in results["questions"]:
            for option in question["options"]:
                self.session.add(
                    MeetingResult(
                        meeting_id=meeting_id,
                        question_id=question["question_id"],
                        option=option["option"],
                        votes_count=option["votes_count"],
                        votes_weight=option["votes_weight"],
                        percent=option["percent"],
                        is_accepted=option["is_accepted"],
                    )
                )

        meeting.status = MeetingStatus.FINISHED
        await self.session.flush()
        log.info("voting.finished", meeting=str(meeting_id))
        return meeting

    async def _complex_area(self, complex_id: uuid.UUID) -> Decimal:
        total = await self.session.scalar(
            select(func.coalesce(func.sum(func.coalesce(Apartment.area_sqm, FALLBACK_AREA)), 0))
            .join(Entrance, Apartment.entrance_id == Entrance.id)
            .join(Building, Entrance.building_id == Building.id)
            .where(Building.complex_id == complex_id, Apartment.is_active.is_(True))
        )
        return Decimal(total or 0)

    # ------------------------------------------------------------------
    # Голосование
    # ------------------------------------------------------------------

    async def vote(
        self, meeting_id: uuid.UUID, user_id: uuid.UUID, payload: VoteIn, ip: str | None
    ) -> Ballot:
        meeting = await self.get(meeting_id)
        now = datetime.now(UTC)

        if meeting.status != MeetingStatus.ACTIVE:
            raise ConflictError("Собрание не идёт")
        if not (meeting.starts_at <= now <= meeting.ends_at):
            raise ConflictError("Голосование закрыто по времени")

        link = await self.session.scalar(
            select(ApartmentResident).where(
                ApartmentResident.user_id == user_id,
                ApartmentResident.apartment_id == payload.apartment_id,
                ApartmentResident.status == ResidentStatus.VERIFIED,
                ApartmentResident.relation == ResidentRelation.OWNER,
            )
        )
        if link is None:
            raise PermissionDeniedError("Голосовать может только подтверждённый собственник")

        existing = await self.session.scalar(
            select(Ballot.id).where(
                Ballot.meeting_id == meeting_id, Ballot.apartment_id == payload.apartment_id
            )
        )
        if existing:
            raise ConflictError("По этой квартире уже проголосовали")

        apartment = await self.session.get(Apartment, payload.apartment_id)
        if apartment is None:
            raise NotFoundError("Квартира не найдена")

        questions = {
            q.id: q
            for q in await self.session.scalars(
                select(MeetingQuestion).where(MeetingQuestion.meeting_id == meeting_id)
            )
        }
        if len(payload.answers) != len(questions):
            raise ValidationError("Нужно ответить на все вопросы повестки")

        ballot = Ballot(
            meeting_id=meeting_id,
            apartment_id=payload.apartment_id,
            user_id=user_id,
            weight=apartment.area_sqm or FALLBACK_AREA,
            submitted_at=now,
            ip_address=ip,
        )
        self.session.add(ballot)
        await self.session.flush()

        for answer in payload.answers:
            question = questions.get(answer.question_id)
            if question is None:
                raise ValidationError("Вопрос не относится к этому собранию")
            if answer.answer not in question.options:
                raise ValidationError(
                    f"Недопустимый вариант ответа: {answer.answer}", options=question.options
                )
            self.session.add(
                BallotAnswer(
                    ballot_id=ballot.id, question_id=question.id, answer=answer.answer
                )
            )

        await self.session.flush()
        log.info("voting.vote_cast", meeting=str(meeting_id), weight=str(ballot.weight))
        return ballot

    async def has_voted(self, meeting_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        return (
            await self.session.scalar(
                select(Ballot.id).where(
                    Ballot.meeting_id == meeting_id, Ballot.user_id == user_id
                )
            )
        ) is not None

    # ------------------------------------------------------------------
    # Подсчёт
    # ------------------------------------------------------------------

    async def results(self, meeting_id: uuid.UUID) -> dict:
        meeting = await self.get(meeting_id)
        total_area = meeting.total_area or await self._complex_area(meeting.complex_id)

        voted_area = Decimal(
            await self.session.scalar(
                select(func.coalesce(func.sum(Ballot.weight), 0)).where(
                    Ballot.meeting_id == meeting_id
                )
            )
            or 0
        )
        apartments_voted = int(
            await self.session.scalar(
                select(func.count(Ballot.id)).where(Ballot.meeting_id == meeting_id)
            )
            or 0
        )

        participation = (
            (voted_area / total_area * 100).quantize(Decimal("0.01"))
            if total_area
            else Decimal(0)
        )
        quorum_reached = participation >= Decimal(meeting.quorum_percent)

        questions = list(
            (
                await self.session.scalars(
                    select(MeetingQuestion)
                    .where(MeetingQuestion.meeting_id == meeting_id)
                    .order_by(MeetingQuestion.order_num)
                )
            ).all()
        )

        question_results = []
        for question in questions:
            rows = await self.session.execute(
                select(
                    BallotAnswer.answer,
                    func.count(BallotAnswer.id),
                    func.coalesce(func.sum(Ballot.weight), 0),
                )
                .join(Ballot, BallotAnswer.ballot_id == Ballot.id)
                .where(BallotAnswer.question_id == question.id)
                .group_by(BallotAnswer.answer)
            )
            tallies = {r[0]: (int(r[1]), Decimal(r[2])) for r in rows.all()}
            threshold = MAJORITY_THRESHOLD[question.majority_type]

            options = []
            decision: str | None = None
            for option in question.options:
                count, weight = tallies.get(option, (0, Decimal(0)))
                # Доля считается от проголосовавшей площади, а не от всей
                percent = (
                    (weight / voted_area * 100).quantize(Decimal("0.01"))
                    if voted_area
                    else Decimal(0)
                )
                accepted = quorum_reached and percent >= threshold
                if accepted:
                    decision = option
                options.append(
                    {
                        "option": option,
                        "votes_count": count,
                        "votes_weight": weight,
                        "percent": percent,
                        "is_accepted": accepted,
                    }
                )

            question_results.append(
                {
                    "question_id": question.id,
                    "text": question.text,
                    "majority_type": question.majority_type,
                    "options": options,
                    "decision": decision,
                }
            )

        return {
            "meeting_id": meeting_id,
            "status": meeting.status,
            "total_area": total_area,
            "voted_area": voted_area,
            "quorum_percent": meeting.quorum_percent,
            "quorum_reached": quorum_reached,
            "participation_percent": participation,
            "apartments_voted": apartments_voted,
            "questions": question_results,
        }

    async def list_for_complexes(self, complex_ids: set[uuid.UUID]) -> list[Meeting]:
        if not complex_ids:
            return []
        result = await self.session.scalars(
            select(Meeting)
            .where(
                Meeting.complex_id.in_(complex_ids),
                Meeting.status != MeetingStatus.DRAFT,
            )
            .order_by(Meeting.starts_at.desc())
        )
        return list(result.all())

    async def organization_of(self, complex_id: uuid.UUID) -> uuid.UUID:
        organization_id = await self.session.scalar(
            select(Complex.organization_id).where(Complex.id == complex_id)
        )
        if organization_id is None:
            raise NotFoundError("Жилой комплекс не найден")
        return organization_id
