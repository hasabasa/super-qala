"""Схемы собраний и голосований."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_OPTIONS = ["За", "Против", "Воздержался"]


class QuestionIn(BaseModel):
    text: str = Field(min_length=3)
    options: list[str] = Field(default_factory=lambda: list(DEFAULT_OPTIONS), min_length=2)
    majority_type: str = Field(default="simple", pattern="^(simple|qualified|unanimous)$")


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_num: int
    text: str
    options: list[str]
    majority_type: str


class MeetingIn(BaseModel):
    complex_id: uuid.UUID
    title: str = Field(max_length=300)
    description: str | None = None
    type: str = Field(default="extraordinary", pattern="^(annual|extraordinary|survey)$")
    starts_at: datetime
    ends_at: datetime
    quorum_percent: int = Field(default=50, ge=1, le=100)
    questions: list[QuestionIn] = Field(min_length=1, max_length=30)


class MeetingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    type: str
    status: str
    starts_at: datetime
    ends_at: datetime
    quorum_percent: int
    protocol_url: str | None
    questions: list[QuestionOut]


class MeetingListOut(BaseModel):
    id: uuid.UUID
    title: str
    type: str
    status: str
    starts_at: datetime
    ends_at: datetime
    has_voted: bool
    questions_count: int


class VoteAnswerIn(BaseModel):
    question_id: uuid.UUID
    answer: str = Field(max_length=100)


class VoteIn(BaseModel):
    apartment_id: uuid.UUID
    answers: list[VoteAnswerIn] = Field(min_length=1)


class BallotOut(BaseModel):
    id: uuid.UUID
    apartment_id: uuid.UUID
    weight: Decimal
    submitted_at: datetime


class OptionResultOut(BaseModel):
    option: str
    votes_count: int
    votes_weight: Decimal
    percent: Decimal
    is_accepted: bool


class QuestionResultOut(BaseModel):
    question_id: uuid.UUID
    text: str
    majority_type: str
    options: list[OptionResultOut]
    decision: str | None


class ResultsOut(BaseModel):
    meeting_id: uuid.UUID
    status: str
    total_area: Decimal
    voted_area: Decimal
    quorum_percent: int
    quorum_reached: bool
    participation_percent: Decimal
    apartments_voted: int
    questions: list[QuestionResultOut]
