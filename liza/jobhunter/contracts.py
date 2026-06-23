from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable

from pydantic import BaseModel

from ..models import CandidateProfile, Vacancy


class MatchResult(BaseModel):
    score: int
    verdict: str
    reasoning: Optional[str] = None


@runtime_checkable
class LLM(Protocol):
    async def complete_json(self, system: str, user: str) -> dict: ...


@runtime_checkable
class VacancySource(Protocol):
    def unscored(self, profile_id: int, limit: int) -> List[Vacancy]: ...


@runtime_checkable
class Scorer(Protocol):
    async def score(self, profile: CandidateProfile, vacancy: Vacancy) -> MatchResult: ...
