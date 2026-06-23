from __future__ import annotations

import asyncio
import logging
from typing import Optional

from ..config import settings
from ..llm.client import LLMClient, LLMError
from ..matching.prefilter import prefilter_reason
from ..matching.scorer import LlmScorer
from ..models import Candidacy
from ..profiles.repo import get_profile
from .repo import save_candidacy
from .source import DbVacancySource

logger = logging.getLogger("liza.jobhunter")

_state = {"in_progress": False, "last_result": None}


def is_matching() -> bool:
    return _state["in_progress"]


def match_status() -> dict:
    return {"in_progress": _state["in_progress"], "last_result": _state["last_result"]}


async def _run(profile, limit, source, scorer) -> dict:
    scored = shortlisted = skipped = errors = 0
    for vac in source.unscored(profile.id, limit):
        if vac is None:
            continue
        reason = prefilter_reason(profile, vac)
        if reason is not None:
            save_candidacy(Candidacy(
                profile_id=profile.id, vacancy_id=vac.id, score=0,
                verdict="skip", reasoning=reason, status="skipped"))
            scored += 1
            skipped += 1
            continue
        try:
            result = await scorer.score(profile, vac)
        except LLMError as err:
            logger.warning("scoring failed for vacancy %s: %s", vac.id, err)
            errors += 1
            continue
        status = "shortlisted" if result.score >= profile.min_score else "skipped"
        save_candidacy(Candidacy(
            profile_id=profile.id, vacancy_id=vac.id, score=result.score,
            verdict=result.verdict, reasoning=result.reasoning, status=status,
            model=getattr(scorer, "model", None)))
        scored += 1
        if status == "shortlisted":
            shortlisted += 1
        else:
            skipped += 1
    pt = getattr(scorer, "prompt_tokens", 0)
    ct = getattr(scorer, "completion_tokens", 0)
    est = round(pt / 1_000_000 * settings.llm_price_in_per_m
                + ct / 1_000_000 * settings.llm_price_out_per_m, 4)
    result = {"scored": scored, "shortlisted": shortlisted, "skipped": skipped,
              "errors": errors, "prompt_tokens": pt, "completion_tokens": ct,
              "est_cost_usd": est}
    _state["last_result"] = result
    logger.info("match done: %s", result)
    return result


async def run_match(profile_id: int, limit: Optional[int] = None, *,
                    source=None, scorer=None) -> dict:
    if _state["in_progress"]:
        return {"skipped": True}
    _state["in_progress"] = True
    limit = limit or settings.match_default_limit
    try:
        profile = get_profile(profile_id)
        if profile is None:
            return {"error": "profile not found"}
        source = source or DbVacancySource()
        if scorer is None:
            async with LLMClient() as llm:
                return await _run(profile, limit, source, LlmScorer(llm))
        return await _run(profile, limit, source, scorer)
    finally:
        _state["in_progress"] = False


def trigger_match(profile_id: int, limit: Optional[int] = None) -> bool:
    if _state["in_progress"]:
        return False
    asyncio.create_task(run_match(profile_id, limit))
    return True
