from __future__ import annotations

from typing import List, Optional

from sqlmodel import Session, select

from ..models import CandidateProfile
from ..storage.repo import get_engine


def create_profile(profile: CandidateProfile) -> CandidateProfile:
    with Session(get_engine()) as session:
        session.add(profile)
        session.commit()
        session.refresh(profile)
        return profile


def get_profile(profile_id: int) -> Optional[CandidateProfile]:
    with Session(get_engine()) as session:
        return session.get(CandidateProfile, profile_id)


def get_by_slug(slug: str) -> Optional[CandidateProfile]:
    with Session(get_engine()) as session:
        return session.scalars(
            select(CandidateProfile).where(CandidateProfile.slug == slug)
        ).first()


def list_profiles() -> List[CandidateProfile]:
    with Session(get_engine()) as session:
        return list(session.scalars(select(CandidateProfile)).all())
