from __future__ import annotations

from typing import Tuple

from ..jobhunter.contracts import MatchResult
from ..models import CandidateProfile, Vacancy

_VERDICTS = {"apply", "consider", "skip"}

SYSTEM_PROMPT = (
    "You are a precise job-fit evaluator. Judge how well a vacancy fits a "
    "candidate based on the ACTUAL responsibilities and requirements in the "
    "description — NOT the job title (titles are often misleading). Consider the "
    "candidate's resume, role focus, and preferences (e.g. remote-only). "
    "Reply ONLY as JSON: {\"score\": 0-100, \"verdict\": \"apply|consider|skip\", "
    "\"reasoning\": \"one short sentence\"}."
)


def build_prompt(profile: CandidateProfile, vacancy: Vacancy) -> Tuple[str, str]:
    prefs = []
    if profile.remote_only:
        prefs.append("remote-only (reject office/hybrid)")
    if profile.role_focus:
        prefs.append("target role: " + profile.role_focus)
    user = (
        "CANDIDATE RESUME:\n" + (profile.resume_md or "") + "\n\n"
        + ("PREFERENCES: " + "; ".join(prefs) + "\n\n" if prefs else "")
        + "VACANCY:\n"
        + "Title: " + (vacancy.title or "") + "\n"
        + "Company: " + (vacancy.company or "") + "\n"
        + "Work format: " + (vacancy.work_format or "unknown") + "\n"
        + "Description:\n" + (vacancy.description or "(none)") + "\n\n"
        + "Score the fit."
    )
    return SYSTEM_PROMPT, user


def normalize_score(raw: dict) -> dict:
    try:
        score = int(raw.get("score", 0))
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(100, score))
    verdict = str(raw.get("verdict", "skip")).lower().strip()
    if verdict not in _VERDICTS:
        verdict = "skip"
    reasoning = raw.get("reasoning")
    return {"score": score, "verdict": verdict,
            "reasoning": str(reasoning) if reasoning is not None else None}


class LlmScorer:
    """Adapter implementing the Scorer contract using an LLM."""

    def __init__(self, llm) -> None:        # llm: contracts.LLM
        self._llm = llm
        self.model = getattr(llm, "model", None)

    async def score(self, profile: CandidateProfile, vacancy: Vacancy) -> MatchResult:
        system, user = build_prompt(profile, vacancy)
        raw = await self._llm.complete_json(system, user)
        return MatchResult(**normalize_score(raw))
