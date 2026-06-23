from __future__ import annotations

from datetime import date, datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, field_serializer
from sqlmodel import Field, SQLModel


# Fields shared by the scraped record and the stored row.
class _VacancyBase(SQLModel):
    url: str
    title: str
    company: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: Optional[str] = None
    category: Optional[str] = None
    work_format: Optional[str] = None
    location: Optional[str] = None
    posted_date: Optional[date] = None
    description: Optional[str] = None
    raw_json: Optional[str] = None


class ParsedVacancy(_VacancyBase):
    """A vacancy as scraped, before persistence (no id/timestamps)."""


class Vacancy(_VacancyBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    url: str = Field(index=True, unique=True)
    first_seen: datetime
    last_seen: datetime


class VacancyRead(BaseModel):
    id: int
    url: str
    title: str
    company: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: Optional[str] = None
    category: Optional[str] = None
    work_format: Optional[str] = None
    location: Optional[str] = None
    posted_date: Optional[date] = None
    description: Optional[str] = None
    first_seen: datetime
    last_seen: datetime

    model_config = {"from_attributes": True}

    @field_serializer("first_seen", "last_seen")
    def _serialize_utc(self, value: datetime) -> str:
        # Stored timestamps are UTC but tz-naive after the SQLite round-trip;
        # mark them explicitly so the API emits unambiguous "+00:00" times.
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()


class VacancyList(BaseModel):
    items: List[VacancyRead]
    total: int


class CandidateProfile(SQLModel, table=True):
    __tablename__ = "candidate_profile"
    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(index=True, unique=True)
    resume_md: str
    skills_md: Optional[str] = None
    voice_md: Optional[str] = None
    remote_only: bool = True
    exclude_keywords_csv: str = ""     # CSV, matched case-insensitively
    role_focus: Optional[str] = None
    min_score: int = 70
    language: str = "uk"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def exclude_keywords(self) -> List[str]:
        return [k.strip().lower() for k in self.exclude_keywords_csv.split(",") if k.strip()]


class Candidacy(SQLModel, table=True):
    __tablename__ = "candidacy"
    id: Optional[int] = Field(default=None, primary_key=True)
    profile_id: int = Field(index=True)
    vacancy_id: int = Field(index=True)
    score: int = 0
    verdict: str = "skip"
    reasoning: Optional[str] = None
    status: str = "scored"
    model: Optional[str] = None
    scored_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CandidacyRead(BaseModel):
    id: int
    profile_id: int
    vacancy_id: int
    score: int
    verdict: str
    reasoning: Optional[str] = None
    status: str
    scored_at: datetime
    title: Optional[str] = None
    company: Optional[str] = None
    url: Optional[str] = None
    work_format: Optional[str] = None
    posted_date: Optional[date] = None

    model_config = {"from_attributes": True}

    @field_serializer("scored_at")
    def _ser_scored_at(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()


class CandidacyList(BaseModel):
    items: List[CandidacyRead]
    total: int


class ProfileRead(BaseModel):
    id: int
    slug: str
    remote_only: bool
    min_score: int
    role_focus: Optional[str] = None
    language: str

    model_config = {"from_attributes": True}
