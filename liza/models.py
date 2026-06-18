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
