from __future__ import annotations

from typing import List

from sqlmodel import Session

from ..models import Vacancy
from ..storage.repo import get_engine
from .repo import unscored_vacancy_ids


class DbVacancySource:
    """VacancySource backed by the LIZA SQLite vacancy table."""

    def unscored(self, profile_id: int, limit: int) -> List[Vacancy]:
        ids = unscored_vacancy_ids(profile_id, limit)
        with Session(get_engine()) as session:
            return [session.get(Vacancy, i) for i in ids]
