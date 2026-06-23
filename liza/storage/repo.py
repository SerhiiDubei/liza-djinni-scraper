from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import event, func
from sqlmodel import Session, SQLModel, create_engine, select

from ..config import settings
from ..models import ParsedVacancy, Vacancy

_engine = None

# Fields copied from a ParsedVacancy onto an existing row on update.
_UPDATABLE = (
    "title", "company", "salary_min", "salary_max", "salary_currency",
    "category", "work_format", "location", "posted_date", "description", "raw_json",
)


def configure(db_path: str) -> None:
    """Point the repo at a specific SQLite file (used by tests)."""
    global _engine
    _engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()


def get_engine():
    global _engine
    if _engine is None:
        configure(settings.db_path)
    return _engine


def init_db() -> None:
    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    _ensure_columns(engine)


def _ensure_columns(engine) -> None:
    """Idempotently add columns introduced after a table was first created."""
    wanted = {"candidate_profile": [("include_keywords_csv", "VARCHAR DEFAULT ''")]}
    with engine.connect() as conn:
        for table, cols in wanted.items():
            existing = {row[1] for row in conn.exec_driver_sql(
                "PRAGMA table_info(" + table + ")")}
            for name, decl in cols:
                if name not in existing:
                    conn.exec_driver_sql(
                        "ALTER TABLE " + table + " ADD COLUMN " + name + " " + decl)
        conn.commit()


def upsert_vacancies(parsed: List[ParsedVacancy]) -> Tuple[int, int]:
    inserted = updated = 0
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as session:
        for p in parsed:
            existing = session.scalars(
                select(Vacancy).where(Vacancy.url == p.url)
            ).first()
            if existing:
                for field in _UPDATABLE:
                    new_value = getattr(p, field)
                    if new_value is not None:   # never clobber with None
                        setattr(existing, field, new_value)
                existing.last_seen = now
                session.add(existing)
                updated += 1
            else:
                session.add(Vacancy(**p.model_dump(), first_seen=now, last_seen=now))
                inserted += 1
        session.commit()
    return inserted, updated


def list_vacancies(
    category: Optional[str] = None,
    company: Optional[str] = None,
    remote: Optional[bool] = None,
    salary_min: Optional[int] = None,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[Vacancy], int]:
    with Session(get_engine()) as session:
        stmt = select(Vacancy)
        if category:
            stmt = stmt.where(Vacancy.category == category)
        if company:
            stmt = stmt.where(Vacancy.company == company)
        if remote is True:
            stmt = stmt.where(Vacancy.work_format == "remote")
        if salary_min is not None:
            stmt = stmt.where(Vacancy.salary_max >= salary_min)
        if q:
            stmt = stmt.where(func.lower(Vacancy.title).contains(q.lower()))
        total = len(session.scalars(stmt).all())
        rows = session.scalars(
            stmt.order_by(Vacancy.posted_date.desc(), Vacancy.id.desc()).limit(limit).offset(offset)
        ).all()
    return list(rows), total


def get_vacancy(vacancy_id: int) -> Optional[Vacancy]:
    with Session(get_engine()) as session:
        return session.get(Vacancy, vacancy_id)


def stats() -> dict:
    with Session(get_engine()) as session:
        total = len(session.scalars(select(Vacancy)).all())
        rows = session.execute(
            select(Vacancy.category, func.count()).group_by(Vacancy.category)
        ).all()
        by_category = {(c or "uncategorized"): n for c, n in rows}
        last = session.scalar(select(func.max(Vacancy.last_seen)))
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return {
        "total": total,
        "by_category": by_category,
        "last_scrape": last.isoformat() if last is not None else None,
    }
