"""Собрания собственников и голосования.

Голос весит по площади квартиры, а не по головам — так требует
законодательство о жилищных отношениях. Один бюллетень от квартиры.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin
from app.shared.enums import MajorityType, MeetingStatus, MeetingType


class Meeting(Base, TimestampMixin):
    __tablename__ = "meetings"
    __table_args__ = (Index("ix_meetings_complex_status", "complex_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    complex_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complexes.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(20), default=MeetingType.EXTRAORDINARY, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=MeetingStatus.DRAFT, nullable=False)

    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quorum_percent: Mapped[int] = mapped_column(
        Integer, default=50, nullable=False, comment="Доля площади для признания собрания состоявшимся"
    )

    total_area: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), comment="Площадь всех квартир на момент запуска — фиксируется"
    )
    protocol_url: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    questions: Mapped[list["MeetingQuestion"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="MeetingQuestion.order_num"
    )


class MeetingQuestion(Base, TimestampMixin):
    __tablename__ = "meeting_questions"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_num: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, nullable=False, comment="Варианты ответа; по умолчанию за/против/воздержался"
    )
    majority_type: Mapped[str] = mapped_column(
        String(20), default=MajorityType.SIMPLE, nullable=False
    )


class Ballot(Base, TimestampMixin):
    """Бюллетень квартиры. Один на квартиру, вес — доля её площади."""

    __tablename__ = "ballots"
    __table_args__ = (
        UniqueConstraint("meeting_id", "apartment_id", name="uq_ballot_apartment"),
        Index("ix_ballots_meeting", "meeting_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False
    )
    apartment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("apartments.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    weight: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, comment="Площадь квартиры на момент голосования"
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45))

    answers: Mapped[list["BallotAnswer"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan"
    )


class BallotAnswer(Base, TimestampMixin):
    __tablename__ = "ballot_answers"
    __table_args__ = (UniqueConstraint("ballot_id", "question_id", name="uq_ballot_answer"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ballot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ballots.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meeting_questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    answer: Mapped[str] = mapped_column(String(100), nullable=False)


class MeetingResult(Base, TimestampMixin):
    """Итог по вопросу. Фиксируется при завершении собрания."""

    __tablename__ = "meeting_results"
    __table_args__ = (UniqueConstraint("question_id", "option", name="uq_meeting_result_option"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meeting_questions.id", ondelete="CASCADE"), nullable=False
    )
    option: Mapped[str] = mapped_column(String(100), nullable=False)
    votes_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    votes_weight: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    is_accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
