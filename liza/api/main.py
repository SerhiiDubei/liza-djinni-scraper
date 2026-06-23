from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from ..config import settings
from ..models import CandidacyList, CandidateProfile, ProfileRead, VacancyList, VacancyRead
from .. import scheduler
from ..storage import repo
from ..profiles import repo as profiles_repo
from ..jobhunter import repo as jobhunter_repo
from .. import jobhunter as _jh  # noqa: F401  (ensures package import)
from ..jobhunter import pipeline as jobhunter_pipeline


@asynccontextmanager
async def lifespan(app: FastAPI):
    repo.init_db()
    if settings.scrape_on_startup:
        scheduler.trigger_scrape(full=False)
    scheduler.start_scheduler()
    yield
    scheduler.shutdown_scheduler()


app = FastAPI(title="LIZA — Djinni vacancies API", lifespan=lifespan)

_STATIC_DIR = Path(__file__).resolve().parents[2] / "static"


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    """Serve the vacancies dashboard (static single-page UI)."""
    return FileResponse(_STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/vacancies", response_model=VacancyList)
def list_vacancies(
    category: Optional[str] = None,
    company: Optional[str] = None,
    remote: Optional[bool] = None,
    salary_min: Optional[int] = None,
    q: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> VacancyList:
    rows, total = repo.list_vacancies(
        category=category, company=company, remote=remote,
        salary_min=salary_min, q=q, limit=limit, offset=offset,
    )
    return VacancyList(items=[VacancyRead.model_validate(r) for r in rows], total=total)


@app.get("/vacancies/{vacancy_id}", response_model=VacancyRead)
def get_vacancy(vacancy_id: int) -> VacancyRead:
    row = repo.get_vacancy(vacancy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    return VacancyRead.model_validate(row)


@app.post("/scrape")
async def scrape_now(full: bool = False) -> dict:
    started = scheduler.trigger_scrape(full)
    return {"status": "started" if started else "already_running", "full": full}


@app.get("/stats")
def stats() -> dict:
    s = repo.stats()
    status = scheduler.scrape_status()
    s["scraping"] = status["in_progress"]
    s["last_result"] = status["last_result"]
    return s


@app.post("/profiles", response_model=ProfileRead)
def create_profile(profile: CandidateProfile) -> ProfileRead:
    saved = profiles_repo.create_profile(profile)
    return ProfileRead.model_validate(saved)


@app.get("/profiles", response_model=list)
def list_profiles() -> list:
    return [ProfileRead.model_validate(p) for p in profiles_repo.list_profiles()]


@app.get("/profiles/{profile_id}", response_model=ProfileRead)
def get_profile(profile_id: int) -> ProfileRead:
    p = profiles_repo.get_profile(profile_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return ProfileRead.model_validate(p)


@app.get("/match-status")
def match_status() -> dict:
    return jobhunter_pipeline.match_status()


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
