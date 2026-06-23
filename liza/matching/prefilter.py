from __future__ import annotations

from typing import Optional

from ..models import CandidateProfile, Vacancy


def prefilter_reason(profile: CandidateProfile, vacancy: Vacancy) -> Optional[str]:
    """Return a drop reason if the vacancy violates a cheap rule, else None.

    Note: remote_only is NOT enforced here — Djinni JSON-LD does not reliably
    distinguish office/hybrid from unknown, so remote suitability is judged by
    the LLM scorer (which reads the description). Here we only drop on explicit
    excluded keywords/industries found in the text.
    """
    haystack = " ".join(filter(None, [vacancy.title, vacancy.company,
                                       vacancy.description])).lower()
    for kw in profile.exclude_keywords:
        if kw in haystack:
            return "excluded keyword: " + kw
    return None
