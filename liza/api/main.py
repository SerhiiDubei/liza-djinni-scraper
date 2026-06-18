from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from ..config import settings
from ..models import VacancyList, VacancyRead
from ..scheduler import scrape_job, shutdown_scheduler, start_scheduler
from ..storage import repo


@asynccontextmanager
async def lifespan(app: FastAPI):
    repo.init_db()
    if settings.scrape_on_startup:
        await scrape_job()
    start_scheduler()
    yield
    shutdown_scheduler()


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
async def scrape_now() -> dict:
    inserted, updated = await scrape_job()
    return {"inserted": inserted, "updated": updated}


@app.get("/stats")
def stats() -> dict:
    return repo.stats()
