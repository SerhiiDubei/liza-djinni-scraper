# Job Hunter v2 — Phase 1 (Profiles + LLM Matching) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** On top of the existing LIZA service, add candidate **profiles** and an **LLM matcher** that scores each vacancy against a profile (resume + preferences), applies a **threshold**, and exposes a ranked **shortlist** via API + a dashboard tab.

**Architecture:** Extend the LIZA FastAPI app + SQLite DB. New tables `candidate_profile` and `candidacy` (profile×vacancy). A cheap rule **pre-filter** runs before any LLM call; survivors are scored by an **OpenRouter** LLM (mockable async client) producing `{score, verdict, reasoning}`. A background **match pipeline** scores only vacancies not yet scored for that profile (score-once), guarded against overlap like the existing scraper.

**Tech Stack:** Python 3.9+, FastAPI, SQLModel, httpx (OpenRouter), pytest. LLM is **always mocked** in the offline suite; live calls need `OPENROUTER_API_KEY`.

**Spec:** [docs/superpowers/specs/2026-06-23-job-hunter-v2-design.md](../specs/2026-06-23-job-hunter-v2-design.md)

**Relevant skills:** @superpowers:test-driven-development · @superpowers:verification-before-completion

---

## File Structure

| File | Responsibility |
|---|---|
| `liza/config.py` (modify) | add OpenRouter + matching settings |
| `liza/models.py` (modify) | `CandidateProfile`, `Candidacy` tables + read schemas |
| `liza/llm/client.py` (create) | async OpenRouter chat client (JSON), retries, mockable |
| `liza/profiles/repo.py` (create) | profile create/get/list |
| `liza/matching/prefilter.py` (create) | cheap rule filter (exclude keywords/industries) |
| `liza/matching/scorer.py` (create) | LLM scoring → `{score, verdict, reasoning}` |
| `liza/jobhunter/repo.py` (create) | candidacy upsert/list/get; unique(profile,vacancy) |
| `liza/jobhunter/pipeline.py` (create) | `run_match` background; prefilter→score→store; counts |
| `liza/api/main.py` (modify) | profiles + run + candidacies endpoints |
| `static/index.html` (modify) | a "Shortlist" tab over `/candidacies` |
| `.env.example`, `README.md` (modify) | document `OPENROUTER_API_KEY` |

**Scoring convention:** `score` is 0–100; `verdict` ∈ {`apply`,`consider`,`skip`}; threshold = `profile.min_score` (default 70). Prefiltered-out vacancies are stored as `status=skipped, score=0`. Every (profile,vacancy) gets exactly one `candidacy` row (score-once).

---

## Task 1: Settings for OpenRouter + matching

**Files:** Modify `liza/config.py`; Test `tests/test_config.py`

- [ ] **Step 1: Write failing test** — append to `tests/test_config.py`:
```python
def test_matching_settings_defaults():
    s = Settings()
    assert s.llm_model_score == "openai/gpt-4o-mini"
    assert s.openrouter_base_url.startswith("https://")
    assert s.match_default_limit > 0
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_config.py -v` → FAIL (attrs missing).

- [ ] **Step 3: Implement** — add these fields to the `Settings` class in `liza/config.py` (keep existing fields):
```python
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_model_score: str = "openai/gpt-4o-mini"
    llm_timeout_sec: float = 60.0
    match_default_limit: int = 50   # vacancies scored per run by default
```

- [ ] **Step 4: Run** `.venv/bin/pytest tests/test_config.py -v` → pass.

- [ ] **Step 5: Commit**
```bash
git add liza/config.py tests/test_config.py
git commit -m "feat(jobhunter): settings for OpenRouter + matching"
```

---

## Task 2: Models — CandidateProfile & Candidacy

**Files:** Modify `liza/models.py`; Test `tests/test_jobhunter_models.py`

- [ ] **Step 1: Write failing test** — `tests/test_jobhunter_models.py`:
```python
from liza.models import CandidateProfile, Candidacy


def test_profile_defaults():
    p = CandidateProfile(slug="serhii", resume_md="CV")
    assert p.min_score == 70
    assert p.remote_only is True
    assert p.language == "uk"


def test_candidacy_is_table():
    assert Candidacy.__tablename__ == "candidacy"
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_jobhunter_models.py -v` → FAIL (import error).

- [ ] **Step 3: Implement** — append to `liza/models.py` (after the existing models; keep imports — `datetime`, `Optional`, `List`, `Field`, `SQLModel`, `BaseModel` are already imported):
```python
class CandidateProfile(SQLModel, table=True):
    __tablename__ = "candidate_profile"
    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(index=True, unique=True)
    resume_md: str
    skills_md: Optional[str] = None
    voice_md: Optional[str] = None
    # preferences (flattened for simplicity)
    remote_only: bool = True
    exclude_keywords_csv: str = ""     # CSV, matched case-insensitively
    role_focus: Optional[str] = None   # free text, fed to the LLM
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
    verdict: str = "skip"          # apply / consider / skip
    reasoning: Optional[str] = None
    status: str = "scored"          # scored/shortlisted/skipped/... (later phases extend)
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
    # joined vacancy fields for display
    title: Optional[str] = None
    company: Optional[str] = None
    url: Optional[str] = None
    work_format: Optional[str] = None
    posted_date: Optional[date] = None

    model_config = {"from_attributes": True}

    @field_serializer("scored_at")
    def _ser_dt(self, value: datetime) -> str:
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
```
> Note: `models.py` already imports `field_serializer`, `timezone`, `date` (added in the UTC change). If a needed name is missing, add it to the existing import lines.

- [ ] **Step 4: Run** `.venv/bin/pytest tests/test_jobhunter_models.py -v` → pass.

- [ ] **Step 5: Commit**
```bash
git add liza/models.py tests/test_jobhunter_models.py
git commit -m "feat(jobhunter): candidate profile + candidacy models"
```

---

## Task 3: OpenRouter LLM client (async, mockable)

**Files:** Create `liza/llm/__init__.py`, `liza/llm/client.py`; Test `tests/test_llm_client.py`

- [ ] **Step 1: Write failing test** — `tests/test_llm_client.py`:
```python
import httpx
import pytest

from liza.llm.client import LLMClient, LLMError


def _resp(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


async def test_complete_json_returns_parsed():
    transport = httpx.MockTransport(lambda req: _resp('{"score": 80, "verdict": "apply"}'))
    async with LLMClient(api_key="x", transport=transport) as c:
        out = await c.complete_json(system="s", user="u")
    assert out == {"score": 80, "verdict": "apply"}


async def test_complete_json_strips_code_fences():
    transport = httpx.MockTransport(lambda req: _resp('```json\n{"a": 1}\n```'))
    async with LLMClient(api_key="x", transport=transport) as c:
        assert await c.complete_json(system="s", user="u") == {"a": 1}


async def test_missing_key_raises():
    with pytest.raises(LLMError):
        async with LLMClient(api_key="") as c:
            await c.complete_json(system="s", user="u")
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_llm_client.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement** — create `liza/llm/__init__.py` (empty) and `liza/llm/client.py`:
```python
from __future__ import annotations

import asyncio
import json
import re
from typing import Optional

import httpx

from ..config import settings


class LLMError(Exception):
    """LLM call failed or returned unparseable output."""


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class LLMClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: int = 3,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.api_key = settings.openrouter_api_key if api_key is None else api_key
        self.model = model or settings.llm_model_score
        self.max_retries = max_retries
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.openrouter_base_url,
            timeout=settings.llm_timeout_sec if timeout is None else timeout,
            transport=transport,
        )

    async def __aenter__(self) -> "LLMClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self._client.aclose()

    async def complete_json(self, system: str, user: str, model: Optional[str] = None) -> dict:
        if not self.api_key:
            raise LLMError("OPENROUTER_API_KEY is not set")
        payload = {
            "model": model or self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": "Bearer " + self.api_key,
                   "Content-Type": "application/json"}
        last: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                r = await self._client.post("/chat/completions", json=payload, headers=headers)
            except httpx.HTTPError as err:
                last = err
                if attempt < self.max_retries:
                    await asyncio.sleep(0.5 * attempt)
                continue
            if r.status_code in (429, 500, 502, 503):
                last = LLMError("HTTP " + str(r.status_code))
                if attempt < self.max_retries:
                    await asyncio.sleep(0.5 * attempt)
                continue
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"].strip()
            content = _FENCE.sub("", content).strip()
            try:
                return json.loads(content)
            except (ValueError, TypeError) as err:
                raise LLMError("Bad JSON from LLM: " + str(err))
        raise LLMError("LLM call failed after retries: " + str(last))
```

- [ ] **Step 4: Run** `.venv/bin/pytest tests/test_llm_client.py -v` → 3 pass.

- [ ] **Step 5: Commit**
```bash
git add liza/llm tests/test_llm_client.py
git commit -m "feat(jobhunter): async OpenRouter JSON client"
```

---

## Task 4: Pre-filter (cheap rules)

**Files:** Create `liza/matching/__init__.py`, `liza/matching/prefilter.py`; Test `tests/test_prefilter.py`

- [ ] **Step 1: Write failing test** — `tests/test_prefilter.py`:
```python
from liza.models import CandidateProfile, Vacancy
from liza.matching.prefilter import prefilter_reason


def _p(**kw):
    return CandidateProfile(slug="p", resume_md="cv", **kw)


def _v(**kw):
    return Vacancy(url="u", title="T", first_seen=None, last_seen=None, **kw)


def test_keeps_normal_vacancy():
    assert prefilter_reason(_p(exclude_keywords_csv="gambling,casino"),
                            _v(title="Python Dev", description="fintech")) is None


def test_drops_on_excluded_keyword():
    reason = prefilter_reason(_p(exclude_keywords_csv="gambling,casino"),
                             _v(title="Casino Backend", description="igaming"))
    assert reason and "casino" in reason.lower()
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_prefilter.py -v` → FAIL.

- [ ] **Step 3: Implement** — `liza/matching/__init__.py` (empty) and `liza/matching/prefilter.py`:
```python
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
```

- [ ] **Step 4: Run** `.venv/bin/pytest tests/test_prefilter.py -v` → pass.

- [ ] **Step 5: Commit**
```bash
git add liza/matching/__init__.py liza/matching/prefilter.py tests/test_prefilter.py
git commit -m "feat(jobhunter): keyword pre-filter"
```

---

## Task 5: LLM scorer

**Files:** Create `liza/matching/scorer.py`; Test `tests/test_scorer.py`

- [ ] **Step 1: Write failing test** — `tests/test_scorer.py`:
```python
from liza.models import CandidateProfile, Vacancy
from liza.matching.scorer import build_prompt, normalize_score


def test_normalize_clamps_and_defaults():
    assert normalize_score({"score": 150, "verdict": "apply"})["score"] == 100
    assert normalize_score({"score": -5, "verdict": "x"})["score"] == 0
    out = normalize_score({"score": 80, "verdict": "weird", "reasoning": "ok"})
    assert out["verdict"] == "skip"   # unknown verdict -> skip
    assert out["reasoning"] == "ok"


def test_build_prompt_includes_resume_and_vacancy():
    p = CandidateProfile(slug="p", resume_md="MY-RESUME", role_focus="PM")
    v = Vacancy(url="u", title="Growth PM", description="own roadmap",
                first_seen=None, last_seen=None)
    system, user = build_prompt(p, v)
    assert "MY-RESUME" in user and "Growth PM" in user
    assert "JSON" in system.upper()
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_scorer.py -v` → FAIL.

- [ ] **Step 3: Implement** — `liza/matching/scorer.py`:
```python
from __future__ import annotations

from typing import Optional, Tuple

from ..llm.client import LLMClient
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


async def score_vacancy(profile: CandidateProfile, vacancy: Vacancy,
                        client: LLMClient) -> dict:
    system, user = build_prompt(profile, vacancy)
    raw = await client.complete_json(system=system, user=user)
    return normalize_score(raw)
```

- [ ] **Step 4: Run** `.venv/bin/pytest tests/test_scorer.py -v` → pass.

- [ ] **Step 5: Commit**
```bash
git add liza/matching/scorer.py tests/test_scorer.py
git commit -m "feat(jobhunter): LLM vacancy scorer + normalization"
```

---

## Task 6: Profiles repo

**Files:** Create `liza/profiles/__init__.py`, `liza/profiles/repo.py`; Test `tests/test_profiles_repo.py`

- [ ] **Step 1: Write failing test** — `tests/test_profiles_repo.py`:
```python
from liza.models import CandidateProfile
from liza.storage import repo as store
from liza.profiles import repo as profiles


def test_create_get_list(tmp_path):
    store.configure(str(tmp_path / "p.db"))
    store.init_db()
    p = profiles.create_profile(CandidateProfile(slug="serhii", resume_md="cv"))
    assert p.id is not None
    assert profiles.get_profile(p.id).slug == "serhii"
    assert profiles.get_by_slug("serhii").id == p.id
    assert len(profiles.list_profiles()) == 1
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_profiles_repo.py -v` → FAIL.

- [ ] **Step 3: Implement** — `liza/profiles/__init__.py` (empty) and `liza/profiles/repo.py`:
```python
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
```
> Reuses LIZA's engine via `storage.repo.get_engine`; `init_db()` already calls `SQLModel.metadata.create_all`, which now also creates the new tables (imported in `models`).

- [ ] **Step 4: Run** `.venv/bin/pytest tests/test_profiles_repo.py -v` → pass.

- [ ] **Step 5: Commit**
```bash
git add liza/profiles tests/test_profiles_repo.py
git commit -m "feat(jobhunter): profiles repo"
```

---

## Task 7: Candidacy repo

**Files:** Create `liza/jobhunter/__init__.py`, `liza/jobhunter/repo.py`; Test `tests/test_candidacy_repo.py`

- [ ] **Step 1: Write failing test** — `tests/test_candidacy_repo.py`:
```python
from datetime import date
from liza.models import Candidacy, ParsedVacancy
from liza.storage import repo as store
from liza.jobhunter import repo as jh


def _seed_vacancies(n):
    store.upsert_vacancies([
        ParsedVacancy(url=f"u{i}", title=f"Job {i}", posted_date=date(2026, 6, i + 1))
        for i in range(n)
    ])


def test_unscored_and_save_and_list(tmp_path):
    store.configure(str(tmp_path / "c.db"))
    store.init_db()
    _seed_vacancies(3)
    rows, _ = store.list_vacancies()
    ids = [r.id for r in rows]

    # initially all 3 are unscored for profile 1
    assert set(jh.unscored_vacancy_ids(profile_id=1, limit=10)) == set(ids)

    jh.save_candidacy(Candidacy(profile_id=1, vacancy_id=ids[0], score=90,
                                verdict="apply", status="shortlisted"))
    # now 2 remain unscored
    assert len(jh.unscored_vacancy_ids(profile_id=1, limit=10)) == 2

    items, total = jh.list_candidacies(profile_id=1)
    assert total == 1 and items[0].score == 90
    assert items[0].title == "Job 0"   # joined vacancy field


def test_list_filters(tmp_path):
    store.configure(str(tmp_path / "c2.db"))
    store.init_db()
    _seed_vacancies(2)
    rows, _ = store.list_vacancies()
    jh.save_candidacy(Candidacy(profile_id=1, vacancy_id=rows[0].id, score=90,
                                verdict="apply", status="shortlisted"))
    jh.save_candidacy(Candidacy(profile_id=1, vacancy_id=rows[1].id, score=20,
                                verdict="skip", status="skipped"))
    assert jh.list_candidacies(profile_id=1, status="shortlisted")[1] == 1
    assert jh.list_candidacies(profile_id=1, min_score=50)[1] == 1
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_candidacy_repo.py -v` → FAIL.

- [ ] **Step 3: Implement** — `liza/jobhunter/__init__.py` (empty) and `liza/jobhunter/repo.py`:
```python
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
```

- [ ] **Step 4: Run** `.venv/bin/pytest tests/test_candidacy_repo.py -v` → pass.

- [ ] **Step 5: Commit**
```bash
git add liza/jobhunter/__init__.py liza/jobhunter/repo.py tests/test_candidacy_repo.py
git commit -m "feat(jobhunter): candidacy repo (score-once, joined list)"
```

---

## Task 8: Match pipeline (background, guarded)

**Files:** Create `liza/jobhunter/pipeline.py`; Test `tests/test_match_pipeline.py`

- [ ] **Step 1: Write failing test** — `tests/test_match_pipeline.py`:
```python
from datetime import date
import liza.jobhunter.pipeline as pipeline
from liza.models import CandidateProfile, ParsedVacancy
from liza.storage import repo as store
from liza.profiles import repo as profiles
from liza.jobhunter import repo as jh


async def test_run_match_scores_and_thresholds(tmp_path, monkeypatch):
    store.configure(str(tmp_path / "m.db"))
    store.init_db()
    store.upsert_vacancies([
        ParsedVacancy(url="good", title="Growth PM", description="own roadmap",
                      posted_date=date(2026, 6, 2)),
        ParsedVacancy(url="bad", title="Casino Dev", description="igaming",
                      posted_date=date(2026, 6, 1)),
    ])
    profiles.create_profile(CandidateProfile(
        slug="serhii", resume_md="PM with growth", min_score=70,
        exclude_keywords_csv="casino"))

    # Fake the LLM scorer: the "good" one scores 88.
    async def fake_score(profile, vacancy, client):
        return {"score": 88, "verdict": "apply", "reasoning": "fit"}
    monkeypatch.setattr(pipeline, "score_vacancy", fake_score)

    res = await pipeline.run_match(profile_id=1, limit=10)
    assert res["scored"] == 2           # 1 prefiltered + 1 LLM-scored
    assert res["shortlisted"] == 1
    assert res["skipped"] == 1

    short, n = jh.list_candidacies(profile_id=1, status="shortlisted")
    assert n == 1 and short[0].title == "Growth PM" and short[0].score == 88
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_match_pipeline.py -v` → FAIL.

- [ ] **Step 3: Implement** — `liza/jobhunter/pipeline.py`:
```python
from __future__ import annotations

import logging
from typing import Optional

from sqlmodel import Session, select

from ..config import settings
from ..llm.client import LLMClient, LLMError
from ..matching.prefilter import prefilter_reason
from ..matching.scorer import score_vacancy
from ..models import Candidacy, Vacancy
from ..profiles.repo import get_profile
from ..storage.repo import get_engine
from .repo import save_candidacy, unscored_vacancy_ids

logger = logging.getLogger("liza.jobhunter")

_state = {"in_progress": False, "last_result": None}


def is_matching() -> bool:
    return _state["in_progress"]


def match_status() -> dict:
    return {"in_progress": _state["in_progress"], "last_result": _state["last_result"]}


def _get_vacancy(vacancy_id: int) -> Optional[Vacancy]:
    with Session(get_engine()) as session:
        return session.get(Vacancy, vacancy_id)


async def run_match(profile_id: int, limit: Optional[int] = None) -> dict:
    if _state["in_progress"]:
        return {"skipped": True}
    _state["in_progress"] = True
    limit = limit or settings.match_default_limit
    scored = shortlisted = skipped = 0
    try:
        profile = get_profile(profile_id)
        if profile is None:
            return {"error": "profile not found"}
        ids = unscored_vacancy_ids(profile_id, limit)
        async with LLMClient() as client:
            for vid in ids:
                vac = _get_vacancy(vid)
                if vac is None:
                    continue
                reason = prefilter_reason(profile, vac)
                if reason is not None:
                    save_candidacy(Candidacy(
                        profile_id=profile_id, vacancy_id=vid, score=0,
                        verdict="skip", reasoning=reason, status="skipped"))
                    scored += 1
                    skipped += 1
                    continue
                try:
                    result = await score_vacancy(profile, vac, client)
                except LLMError as err:
                    logger.warning("scoring failed for vacancy %s: %s", vid, err)
                    continue
                status = "shortlisted" if result["score"] >= profile.min_score else "skipped"
                save_candidacy(Candidacy(
                    profile_id=profile_id, vacancy_id=vid, score=result["score"],
                    verdict=result["verdict"], reasoning=result["reasoning"],
                    status=status, model=client.model))
                scored += 1
                if status == "shortlisted":
                    shortlisted += 1
                else:
                    skipped += 1
        result = {"scored": scored, "shortlisted": shortlisted, "skipped": skipped}
        _state["last_result"] = result
        logger.info("match done for profile %s: %s", profile_id, result)
        return result
    finally:
        _state["in_progress"] = False


def trigger_match(profile_id: int, limit: Optional[int] = None) -> bool:
    import asyncio
    if _state["in_progress"]:
        return False
    asyncio.create_task(run_match(profile_id, limit))
    return True
```

- [ ] **Step 4: Run** `.venv/bin/pytest tests/test_match_pipeline.py -v` → pass.

- [ ] **Step 5: Commit**
```bash
git add liza/jobhunter/pipeline.py tests/test_match_pipeline.py
git commit -m "feat(jobhunter): match pipeline (prefilter+score+threshold, guarded)"
```

---

## Task 9: API endpoints

**Files:** Modify `liza/api/main.py`; Test `tests/test_jobhunter_api.py`

- [ ] **Step 1: Write failing test** — `tests/test_jobhunter_api.py`:
```python
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ENABLE_SCHEDULER", "false")
    monkeypatch.setenv("SCRAPE_ON_STARTUP", "false")
    from liza.config import settings
    settings.enable_scheduler = False
    settings.scrape_on_startup = False
    from liza.storage import repo
    repo.configure(str(tmp_path / "api.db"))
    repo.init_db()
    from liza.api.main import app
    with TestClient(app) as c:
        yield c


def test_profile_crud_and_run(client, monkeypatch):
    r = client.post("/profiles", json={"slug": "serhii", "resume_md": "PM",
                                       "min_score": 70})
    assert r.status_code == 200
    pid = r.json()["id"]
    assert client.get(f"/profiles/{pid}").json()["slug"] == "serhii"

    import liza.jobhunter.pipeline as pipeline
    calls = {}
    def fake_trigger(profile_id, limit=None):
        calls["pid"] = profile_id
        return True
    monkeypatch.setattr(pipeline, "trigger_match", fake_trigger)
    body = client.post(f"/profiles/{pid}/run").json()
    assert body["status"] == "started" and calls["pid"] == pid


def test_candidacies_empty(client):
    r = client.post("/profiles", json={"slug": "x", "resume_md": "cv"})
    pid = r.json()["id"]
    body = client.get("/candidacies", params={"profile": pid}).json()
    assert body == {"items": [], "total": 0}
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_jobhunter_api.py -v` → FAIL.

- [ ] **Step 3: Implement** — add to `liza/api/main.py`:
  - imports near the top:
```python
from ..models import CandidateProfile, ProfileRead, CandidacyList, CandidacyRead
from ..profiles import repo as profiles_repo
from ..jobhunter import repo as jobhunter_repo
from ..jobhunter import pipeline as jobhunter_pipeline
```
  - endpoints (append after the existing routes):
```python
@app.post("/profiles", response_model=ProfileRead)
def create_profile(profile: CandidateProfile) -> ProfileRead:
    saved = profiles_repo.create_profile(profile)
    return ProfileRead.model_validate(saved)


@app.get("/profiles", response_model=list[ProfileRead])
def list_profiles() -> list:
    return [ProfileRead.model_validate(p) for p in profiles_repo.list_profiles()]


@app.get("/profiles/{profile_id}", response_model=ProfileRead)
def get_profile(profile_id: int) -> ProfileRead:
    p = profiles_repo.get_profile(profile_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return ProfileRead.model_validate(p)


@app.post("/profiles/{profile_id}/run")
async def run_match(profile_id: int, limit: Optional[int] = None) -> dict:
    if profiles_repo.get_profile(profile_id) is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    started = jobhunter_pipeline.trigger_match(profile_id, limit)
    return {"status": "started" if started else "already_running"}


@app.get("/candidacies", response_model=CandidacyList)
def list_candidacies(
    profile: int,
    status: Optional[str] = None,
    min_score: Optional[int] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> CandidacyList:
    items, total = jobhunter_repo.list_candidacies(
        profile_id=profile, status=status, min_score=min_score,
        limit=limit, offset=offset)
    return CandidacyList(items=items, total=total)
```

- [ ] **Step 4: Run** `.venv/bin/pytest tests/test_jobhunter_api.py -v` → pass. Then full suite `.venv/bin/pytest -q -m "not network"`.

- [ ] **Step 5: Commit**
```bash
git add liza/api/main.py tests/test_jobhunter_api.py
git commit -m "feat(jobhunter): profiles + match + candidacies API"
```

---

## Task 10: Config docs + dashboard shortlist tab

**Files:** Modify `.env.example`, `README.md`, `static/index.html`

- [ ] **Step 1:** Add to `.env.example`:
```bash
# OpenRouter (job-hunter LLM matching). Get a key at https://openrouter.ai/keys
OPENROUTER_API_KEY=
LLM_MODEL_SCORE=openai/gpt-4o-mini
```

- [ ] **Step 2:** In `static/index.html`, add a minimal **Shortlist** section that, given a profile id, fetches `/candidacies?profile=<id>&status=shortlisted` and renders a table (score, title→url, company, verdict, reasoning). **Use safe DOM construction (createElement/textContent), NOT innerHTML.** Add a profile-id input + "Завантажити" button + "Запустити метч" button (POST `/profiles/{id}/run`). Reuse the page's existing dark styles.

- [ ] **Step 3:** Update `README.md`: a "Job Hunter (matching)" section — what it does, env (`OPENROUTER_API_KEY`), endpoints (`/profiles`, `/profiles/{id}/run`, `/candidacies`), and that scoring is LLM-based + score-once + threshold.

- [ ] **Step 4:** Run full suite `.venv/bin/pytest -q -m "not network"` → all pass.

- [ ] **Step 5: Commit**
```bash
git add .env.example README.md static/index.html
git commit -m "feat(jobhunter): docs + dashboard shortlist tab"
```

---

## Done criteria (Phase 1)
- `.venv/bin/pytest -m "not network"` green (existing + new tests).
- Can create a profile, trigger a match run, and read a ranked shortlist via API/dashboard.
- LLM is mocked in tests; live scoring works once `OPENROUTER_API_KEY` is set in Railway.
- Score-once holds (re-running only scores new vacancies); prefiltered vacancies stored as `skipped`.

## Out of scope (later phases)
- Phase 2: enforced company research + composable cover letters + review.
- Phase 3: funnel status transitions + semi-auto send (Claude-in-Chrome, human-confirmed).
