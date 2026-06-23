from __future__ import annotations

from typing import List, Optional, Tuple

from sqlmodel import Session, select

from ..models import Candidacy, CandidacyRead, Vacancy
from ..storage.repo import get_engine


def unscored_vacancy_ids(profile_id: int, limit: int) -> List[int]:
    """Vacancy ids that have no candidacy row yet for this profile (score-once)."""
    with Session(get_engine()) as session:
        scored = select(Candidacy.vacancy_id).where(Candidacy.profile_id == profile_id)
        stmt = (select(Vacancy.id)
                .where(Vacancy.id.not_in(scored))
                .order_by(Vacancy.posted_date.desc(), Vacancy.id.desc())
                .limit(limit))
        return list(session.scalars(stmt).all())


def save_candidacy(c: Candidacy) -> Candidacy:
    with Session(get_engine()) as session:
        session.add(c)
        session.commit()
        session.refresh(c)
        return c


def list_candidacies(
    profile_id: int,
    status: Optional[str] = None,
    min_score: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[CandidacyRead], int]:
    with Session(get_engine()) as session:
        stmt = (select(Candidacy, Vacancy)
                .join(Vacancy, Vacancy.id == Candidacy.vacancy_id)
                .where(Candidacy.profile_id == profile_id))
        if status:
            stmt = stmt.where(Candidacy.status == status)
        if min_score is not None:
            stmt = stmt.where(Candidacy.score >= min_score)
        all_rows = session.execute(stmt).all()
        total = len(all_rows)
        page = session.execute(
            stmt.order_by(Candidacy.score.desc(), Candidacy.id.desc())
            .limit(limit).offset(offset)
        ).all()
        items = []
        for cand, vac in page:
            items.append(CandidacyRead(
                id=cand.id, profile_id=cand.profile_id, vacancy_id=cand.vacancy_id,
                score=cand.score, verdict=cand.verdict, reasoning=cand.reasoning,
                status=cand.status, scored_at=cand.scored_at,
                title=vac.title, company=vac.company, url=vac.url,
                work_format=vac.work_format, posted_date=vac.posted_date,
            ))
    return items, total
