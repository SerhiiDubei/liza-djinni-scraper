# Djinni Scraper + API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-hosted Python service that scrapes the public Djinni jobs catalog via JSON-LD on a schedule, stores vacancies in SQLite with deduplication, and serves them over a FastAPI HTTP API.

**Architecture:** A pure JSON-LD parser (the durable core) feeds an async httpx scraper; an APScheduler job periodically scrapes and upserts into SQLite (dedup by URL); FastAPI reads from SQLite and exposes filtered, paginated endpoints. Clean layer separation: `scraper/` (fetch+parse), `storage/` (persist), `scheduler.py` (orchestrate), `api/` (serve).

**Tech Stack:** Python 3.9+, FastAPI, uvicorn, httpx, BeautifulSoup4 + lxml, SQLModel, APScheduler, pydantic-settings, pytest + pytest-asyncio.

**Spec:** [docs/superpowers/specs/2026-06-17-djinni-scraper-api-design.md](../specs/2026-06-17-djinni-scraper-api-design.md)

**Relevant skills:** @superpowers:test-driven-development · @superpowers:verification-before-completion

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, deps, pytest config |
| `.env.example` | Documented configuration template |
| `liza/config.py` | `Settings` (env-driven) |
| `liza/models.py` | `ParsedVacancy` (scraped), `Vacancy` (DB row), `VacancyRead`/`VacancyList` (API) |
| `liza/scraper/parser.py` | JSON-LD → `ParsedVacancy`; total-page detection (pure, no I/O) |
| `liza/scraper/client.py` | Async httpx client: UA, delay, backoff, `BlockedError` |
| `liza/scraper/djinni.py` | `fetch_vacancies` / `fetch_all`: pagination, dedup |
| `liza/storage/repo.py` | SQLite engine, `upsert_vacancies`, `list_vacancies`, `get_vacancy`, `stats` |
| `liza/scheduler.py` | APScheduler job: scrape → upsert |
| `liza/api/main.py` | FastAPI app + lifespan + endpoints |
| `tests/fixtures/djinni_jobs.html` | Deterministic offline fixture |
| `tests/test_*.py` | Unit tests per module |

---

## Task 1: Project scaffold & dependencies

**Files:**
- Create: `pyproject.toml`, `.env.example`, `liza/__init__.py`, `liza/scraper/__init__.py`, `liza/storage/__init__.py`, `liza/api/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "liza"
version = "0.1.0"
description = "Djinni vacancies scraper + API"
requires-python = ">=3.9"
dependencies = [
    "fastapi",
    "uvicorn[standard]",
    "httpx",
    "beautifulsoup4",
    "lxml",
    "sqlmodel",
    "apscheduler",
    "pydantic-settings",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio"]

[tool.setuptools.packages.find]
include = ["liza*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = ["network: live tests that hit djinni.co (skipped by default)"]
```

- [ ] **Step 2: Create `.env.example`**

```bash
DJINNI_BASE_URL=https://djinni.co
SCRAPE_INTERVAL_MIN=60
DJINNI_KEYWORDS=
MAX_PAGES=
REQUEST_DELAY_SEC=2.0
DB_PATH=./liza.db
DJINNI_COOKIE=
# USER_AGENT=        # optional; config.py provides a sensible default
ENABLE_SCHEDULER=true
SCRAPE_ON_STARTUP=true
```

- [ ] **Step 3: Create empty package files**

Create empty `liza/__init__.py`, `liza/scraper/__init__.py`, `liza/storage/__init__.py`, `liza/api/__init__.py`, `tests/__init__.py`.

- [ ] **Step 4: Create venv and install (editable)**

Run:
```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"
```
Expected: pip upgrades to ≥23, then installs liza and deps with no errors. (Editable install needs pip ≥21.3 — the upgrade step ensures this.)

- [ ] **Step 5: Verify pytest runs (no tests yet)**

Run: `.venv/bin/pytest -q`
Expected: "no tests ran" (exit 5) — confirms the env works.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .env.example liza tests
git commit -m "chore: project scaffold and dependencies"
```

> All later commands use `.venv/bin/pytest` and `.venv/bin/python`.

---

## Task 2: Configuration (`liza/config.py`)

**Files:**
- Create: `liza/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from liza.config import Settings


def test_keywords_list_splits_csv_and_trims():
    s = Settings(djinni_keywords="Python, JavaScript ,, QA")
    assert s.keywords_list == ["Python", "JavaScript", "QA"]


def test_keywords_list_empty_when_blank():
    s = Settings(djinni_keywords="")
    assert s.keywords_list == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'liza.config'`

- [ ] **Step 3: Implement `liza/config.py`**

```python
from __future__ import annotations

from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    djinni_base_url: str = "https://djinni.co"
    scrape_interval_min: int = 60
    djinni_keywords: str = ""           # CSV; empty = all categories
    max_pages: Optional[int] = None     # safety cap; None = until last page
    request_delay_sec: float = 2.0
    db_path: str = "./liza.db"
    djinni_cookie: str = ""             # optional sessionid; empty = anonymous
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    enable_scheduler: bool = True
    scrape_on_startup: bool = True

    @property
    def keywords_list(self) -> List[str]:
        return [k.strip() for k in self.djinni_keywords.split(",") if k.strip()]


settings = Settings()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add liza/config.py tests/test_config.py
git commit -m "feat: env-driven settings"
```

---

## Task 3: Data models (`liza/models.py`)

**Files:**
- Create: `liza/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
from liza.models import ParsedVacancy, Vacancy


def test_parsed_vacancy_requires_only_url_and_title():
    p = ParsedVacancy(url="https://djinni.co/jobs/1/", title="Dev")
    assert p.url.endswith("/1/")
    assert p.company is None
    assert p.salary_min is None


def test_vacancy_is_a_table_model():
    assert Vacancy.__tablename__ == "vacancy"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'liza.models'`

- [ ] **Step 3: Implement `liza/models.py`**

```python
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel
from sqlmodel import Field, SQLModel


# Fields shared by the scraped record and the stored row.
class _VacancyBase(SQLModel):
    url: str
    title: str
    company: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: Optional[str] = None
    category: Optional[str] = None
    work_format: Optional[str] = None
    location: Optional[str] = None
    posted_date: Optional[date] = None
    description: Optional[str] = None
    raw_json: Optional[str] = None


class ParsedVacancy(_VacancyBase):
    """A vacancy as scraped, before persistence (no id/timestamps)."""


class Vacancy(_VacancyBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    url: str = Field(index=True, unique=True)
    first_seen: datetime
    last_seen: datetime


class VacancyRead(BaseModel):
    id: int
    url: str
    title: str
    company: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: Optional[str] = None
    category: Optional[str] = None
    work_format: Optional[str] = None
    location: Optional[str] = None
    posted_date: Optional[date] = None
    description: Optional[str] = None
    first_seen: datetime
    last_seen: datetime

    model_config = {"from_attributes": True}


class VacancyList(BaseModel):
    items: List[VacancyRead]
    total: int
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_models.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add liza/models.py tests/test_models.py
git commit -m "feat: vacancy models (parsed, table, api)"
```

---

## Task 4: JSON-LD parser (`liza/scraper/parser.py`) — the durable core

**Files:**
- Create: `tests/fixtures/djinni_jobs.html`, `liza/scraper/parser.py`
- Test: `tests/test_parser.py`

- [ ] **Step 1: Create the offline fixture `tests/fixtures/djinni_jobs.html`**

```html
<!doctype html>
<html><head>
<script type="application/ld+json">
{"@context":"http://schema.org","@type":"BreadcrumbList","itemListElement":[]}
</script>
<script type="application/ld+json">
{"@context":"http://schema.org","@type":"JobPosting","title":"Senior Python Developer","description":"<p>Great <b>role</b></p>","datePosted":"2026-02-15","employmentType":"FULL_TIME","jobLocationType":"TELECOMMUTE","hiringOrganization":{"@type":"Organization","name":"ACME Corp"},"jobLocation":{"@type":"Place","address":{"@type":"PostalAddress","addressLocality":"Kyiv","addressCountry":"UA"}},"baseSalary":{"@type":"MonetaryAmount","currency":"USD","value":{"@type":"QuantitativeValue","minValue":4000,"maxValue":6000,"unitText":"MONTH"}},"url":"https://djinni.co/jobs/123-senior-python-developer/"}
</script>
<script type="application/ld+json">
{"@context":"http://schema.org","@type":"JobPosting","title":"Junior QA Engineer","description":"QA role","datePosted":"2026-02-14","hiringOrganization":{"@type":"Organization","name":"Beta LLC"},"baseSalary":{"@type":"MonetaryAmount","currency":"USD","value":{"@type":"QuantitativeValue","value":1500}},"url":"https://djinni.co/jobs/456-junior-qa-engineer/"}
</script>
</head><body>
<nav class="pagination">
  <a href="?page=1">1</a>
  <a href="?page=2">2</a>
  <a href="?page=3">3</a>
</nav>
</body></html>
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_parser.py
from pathlib import Path

from liza.scraper.parser import parse_jobs_page

FIXTURE = Path(__file__).parent / "fixtures" / "djinni_jobs.html"


def test_parses_jobpostings_and_skips_other_jsonld():
    vacancies, total_pages = parse_jobs_page(FIXTURE.read_text(encoding="utf-8"))
    assert len(vacancies) == 2          # BreadcrumbList ignored
    assert total_pages == 3

    a = vacancies[0]
    assert a.title == "Senior Python Developer"
    assert a.company == "ACME Corp"
    assert a.url == "https://djinni.co/jobs/123-senior-python-developer/"
    assert a.salary_min == 4000 and a.salary_max == 6000
    assert a.salary_currency == "USD"
    assert a.work_format == "remote"
    assert str(a.posted_date) == "2026-02-15"
    assert a.location == "Kyiv, UA"
    assert "Great role" in a.description    # HTML stripped
    assert a.raw_json is not None


def test_scalar_salary_sets_min_equals_max():
    vacancies, _ = parse_jobs_page(FIXTURE.read_text(encoding="utf-8"))
    b = vacancies[1]
    assert b.salary_min == 1500 and b.salary_max == 1500


def test_empty_page_returns_no_vacancies_and_one_page():
    vacancies, total_pages = parse_jobs_page("<html><body>No jobs</body></html>")
    assert vacancies == []
    assert total_pages == 1
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'liza.scraper.parser'`

- [ ] **Step 4: Implement `liza/scraper/parser.py`**

```python
from __future__ import annotations

import json
import re
from datetime import date
from typing import Iterator, List, Optional, Tuple

from bs4 import BeautifulSoup

from ..models import ParsedVacancy


def parse_jobs_page(html: str) -> Tuple[List[ParsedVacancy], int]:
    """Extract JobPosting records and the total page count from a jobs page.

    Uses BeautifulSoup only to locate <script type="application/ld+json"> tags;
    all vacancy data comes from the parsed JSON-LD, not CSS classes.
    """
    soup = BeautifulSoup(html, "lxml")
    vacancies: List[ParsedVacancy] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue
        for jp in _iter_jobpostings(data):
            vacancies.append(_to_vacancy(jp))
    return vacancies, _total_pages(soup)


def _iter_jobpostings(data) -> Iterator[dict]:
    if isinstance(data, list):
        for item in data:
            yield from _iter_jobpostings(item)
    elif isinstance(data, dict):
        if "@graph" in data:
            yield from _iter_jobpostings(data["@graph"])
        elif data.get("@type") == "JobPosting":
            yield data


def _to_vacancy(jp: dict) -> ParsedVacancy:
    smin, smax, currency = _salary(jp.get("baseSalary"))
    return ParsedVacancy(
        url=jp.get("url") or "",
        title=jp.get("title") or "",
        company=_company(jp.get("hiringOrganization")),
        salary_min=smin,
        salary_max=smax,
        salary_currency=currency,
        work_format="remote" if jp.get("jobLocationType") == "TELECOMMUTE" else None,
        location=_location(jp.get("jobLocation")),
        posted_date=_date(jp.get("datePosted")),
        description=_text(jp.get("description")),
        raw_json=json.dumps(jp, ensure_ascii=False),
    )


def _company(org) -> Optional[str]:
    if isinstance(org, dict):
        return org.get("name")
    if isinstance(org, str):
        return org
    return None


def _salary(base) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    if not isinstance(base, dict):
        return None, None, None
    currency = base.get("currency")
    value = base.get("value")
    if isinstance(value, dict):
        mn, mx = _int(value.get("minValue")), _int(value.get("maxValue"))
        scalar = _int(value.get("value"))
        if mn is None and mx is None and scalar is not None:
            mn = mx = scalar
        return mn, mx, currency
    scalar = _int(value)
    if scalar is not None:
        return scalar, scalar, currency
    return None, None, currency


def _location(loc) -> Optional[str]:
    if isinstance(loc, list):
        loc = loc[0] if loc else None
    if not isinstance(loc, dict):
        return None
    addr = loc.get("address")
    if isinstance(addr, dict):
        parts = [addr.get("addressLocality"), addr.get("addressCountry")]
        joined = ", ".join(p for p in parts if p)
        return joined or None
    return None


def _date(value) -> Optional[date]:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _text(value) -> Optional[str]:
    if not value:
        return None
    return BeautifulSoup(str(value), "lxml").get_text(" ", strip=True) or None


def _int(value) -> Optional[int]:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _total_pages(soup) -> int:
    pages = {1}
    for a in soup.select('a[href*="page="]'):
        m = re.search(r"[?&]page=(\d+)", a.get("href", ""))
        if m:
            pages.add(int(m.group(1)))
    return max(pages)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_parser.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add liza/scraper/parser.py tests/test_parser.py tests/fixtures/djinni_jobs.html
git commit -m "feat: JSON-LD jobs parser with offline fixture"
```

---

## Task 5: HTTP client (`liza/scraper/client.py`)

**Files:**
- Create: `liza/scraper/client.py`
- Test: `tests/test_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_client.py
import httpx
import pytest

from liza.scraper.client import BlockedError, DjinniClient


async def test_get_returns_body_text():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, text="<html>ok</html>"))
    async with DjinniClient(delay=0, transport=transport) as c:
        assert "ok" in await c.get("/jobs/", params={"page": 1})


async def test_get_raises_blocked_on_429():
    transport = httpx.MockTransport(lambda req: httpx.Response(429, text="nope"))
    async with DjinniClient(delay=0, max_retries=2, transport=transport) as c:
        with pytest.raises(BlockedError):
            await c.get("/jobs/")


async def test_get_sends_user_agent_and_cookie():
    seen = {}

    def handler(req):
        seen["ua"] = req.headers.get("user-agent")
        seen["cookie"] = req.headers.get("cookie")
        return httpx.Response(200, text="ok")

    transport = httpx.MockTransport(handler)
    async with DjinniClient(delay=0, user_agent="UA/1", cookie="sessionid=abc",
                            transport=transport) as c:
        await c.get("/jobs/")
    assert seen["ua"] == "UA/1"
    assert seen["cookie"] == "sessionid=abc"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'liza.scraper.client'`

- [ ] **Step 3: Implement `liza/scraper/client.py`**

```python
from __future__ import annotations

import asyncio
from typing import Optional

import httpx

from ..config import settings


class BlockedError(Exception):
    """Raised when Djinni blocks the scraper (HTTP 403/429 after retries)."""


class DjinniClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        user_agent: Optional[str] = None,
        delay: Optional[float] = None,
        cookie: Optional[str] = None,
        max_retries: int = 3,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.delay = settings.request_delay_sec if delay is None else delay
        self.max_retries = max_retries
        headers = {"User-Agent": user_agent or settings.user_agent}
        cookie = settings.djinni_cookie if cookie is None else cookie
        if cookie:
            headers["Cookie"] = cookie
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.djinni_base_url,
            headers=headers,
            timeout=30.0,
            follow_redirects=True,
            transport=transport,
        )

    async def __aenter__(self) -> "DjinniClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self._client.aclose()

    async def get(self, path: str, params: Optional[dict] = None) -> str:
        last: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            if self.delay:
                await asyncio.sleep(self.delay)
            try:
                resp = await self._client.get(path, params=params)
            except httpx.HTTPError as err:
                last = err
                continue
            if resp.status_code in (403, 429):
                last = BlockedError(f"HTTP {resp.status_code} from {path}")
                await asyncio.sleep(self.delay * attempt)
                continue
            if resp.status_code >= 500:
                last = httpx.HTTPStatusError("server error", request=resp.request,
                                             response=resp)
                await asyncio.sleep(self.delay * attempt)
                continue
            resp.raise_for_status()
            return resp.text
        if isinstance(last, BlockedError):
            raise last
        raise BlockedError(
            f"Failed to GET {path} after {self.max_retries} attempts: {last}"
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_client.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add liza/scraper/client.py tests/test_client.py
git commit -m "feat: polite async http client with block detection"
```

---

## Task 6: Scraper orchestration (`liza/scraper/djinni.py`)

**Files:**
- Create: `liza/scraper/djinni.py`
- Test: `tests/test_djinni.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_djinni.py
import httpx

from liza.scraper.djinni import fetch_all, fetch_vacancies

PAGE1 = """
<html><head>
<script type="application/ld+json">
{"@type":"JobPosting","title":"Python Dev","url":"https://djinni.co/jobs/1/",
 "hiringOrganization":{"name":"ACME"}}
</script>
</head><body>
<a href="?page=1">1</a><a href="?page=2">2</a>
</body></html>
"""
EMPTY = "<html><body>nothing</body></html>"


def _transport():
    def handler(req):
        page = req.url.params.get("page", "1")
        return httpx.Response(200, text=PAGE1 if page == "1" else EMPTY)
    return httpx.MockTransport(handler)


async def test_fetch_vacancies_paginates_and_tags_category():
    vacancies = await fetch_vacancies(keyword="Python", transport=_transport())
    assert len(vacancies) == 1
    assert vacancies[0].title == "Python Dev"
    assert vacancies[0].category == "Python"   # tagged from keyword


async def test_fetch_all_dedups_across_keywords_by_url():
    out = await fetch_all(keywords=["Python", "Django"], transport=_transport())
    assert len(out) == 1   # same url from both keyword runs collapses to one
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_djinni.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'liza.scraper.djinni'`

- [ ] **Step 3: Implement `liza/scraper/djinni.py`**

```python
from __future__ import annotations

from typing import Dict, List, Optional

import httpx

from ..config import settings
from ..models import ParsedVacancy
from .client import DjinniClient
from .parser import parse_jobs_page


async def fetch_vacancies(
    keyword: Optional[str] = None,
    max_pages: Optional[int] = None,
    transport: Optional[httpx.BaseTransport] = None,
) -> List[ParsedVacancy]:
    cap = max_pages if max_pages is not None else settings.max_pages
    results: Dict[str, ParsedVacancy] = {}
    async with DjinniClient(transport=transport) as client:
        page = 1
        while True:
            params: Dict[str, object] = {"page": page}
            if keyword:
                params["primary_keyword"] = keyword
            html = await client.get("/jobs/", params=params)
            vacancies, total_pages = parse_jobs_page(html)
            if not vacancies:
                break
            for v in vacancies:
                if keyword and not v.category:
                    v.category = keyword
                if v.url:
                    results[v.url] = v
            limit = min(cap, total_pages) if cap else total_pages
            if page >= limit:
                break
            page += 1
    return list(results.values())


async def fetch_all(
    keywords: Optional[List[str]] = None,
    max_pages: Optional[int] = None,
    transport: Optional[httpx.BaseTransport] = None,
) -> List[ParsedVacancy]:
    keywords = keywords or []
    if not keywords:
        return await fetch_vacancies(None, max_pages, transport)
    merged: Dict[str, ParsedVacancy] = {}
    for kw in keywords:
        for v in await fetch_vacancies(kw, max_pages, transport):
            merged[v.url] = v
    return list(merged.values())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_djinni.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add liza/scraper/djinni.py tests/test_djinni.py
git commit -m "feat: paginated scraper with cross-keyword dedup"
```

---

## Task 7: Storage (`liza/storage/repo.py`)

> SQLModel note: this module uses SQLAlchemy 2.0 style — `session.scalars(stmt)`
> for ORM-object queries and `session.execute(stmt)` for multi-column rows.
> (`session.exec()` would also work but is avoided here.)

**Files:**
- Create: `liza/storage/repo.py`
- Test: `tests/test_repo.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_repo.py
from liza.models import ParsedVacancy
from liza.storage import repo


def _setup(tmp_path):
    repo.configure(str(tmp_path / "test.db"))
    repo.init_db()


def test_upsert_inserts_then_updates_same_url(tmp_path):
    _setup(tmp_path)
    p = ParsedVacancy(url="https://djinni.co/jobs/1/", title="Python Dev",
                      category="Python", work_format="remote", salary_max=5000)
    assert repo.upsert_vacancies([p]) == (1, 0)

    rows, _ = repo.list_vacancies()
    first_seen = rows[0].first_seen

    assert repo.upsert_vacancies([p]) == (0, 1)   # same url -> update
    rows, total = repo.list_vacancies()
    assert total == 1
    assert rows[0].first_seen == first_seen        # first_seen preserved
    assert rows[0].last_seen >= first_seen


def test_list_vacancies_filters(tmp_path):
    _setup(tmp_path)
    repo.upsert_vacancies([
        ParsedVacancy(url="u1", title="Senior Python Dev", category="Python",
                      work_format="remote", salary_max=6000),
        ParsedVacancy(url="u2", title="QA Manual", category="QA", salary_max=2000),
    ])
    assert repo.list_vacancies(category="Python")[1] == 1
    assert repo.list_vacancies(remote=True)[1] == 1
    assert repo.list_vacancies(q="python")[1] == 1        # case-insensitive contains
    assert repo.list_vacancies(salary_min=5000)[1] == 1

    rows, _ = repo.list_vacancies()
    assert repo.get_vacancy(rows[0].id) is not None
    assert repo.get_vacancy(999999) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_repo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'liza.storage.repo'`

- [ ] **Step 3: Implement `liza/storage/repo.py`**

```python
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import func
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
    _engine = create_engine(f"sqlite:///{db_path}",
                            connect_args={"check_same_thread": False})


def get_engine():
    global _engine
    if _engine is None:
        configure(settings.db_path)
    return _engine


def init_db() -> None:
    SQLModel.metadata.create_all(get_engine())


def upsert_vacancies(parsed: List[ParsedVacancy]) -> Tuple[int, int]:
    inserted = updated = 0
    now = datetime.utcnow()
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
    keyword: Optional[str] = None,
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
        if keyword:
            stmt = stmt.where(func.lower(Vacancy.title).contains(keyword.lower()))
        total = len(session.scalars(stmt).all())
        rows = session.scalars(
            stmt.order_by(Vacancy.last_seen.desc()).limit(limit).offset(offset)
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
    return {"total": total, "by_category": by_category, "last_scrape": last}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_repo.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add liza/storage/repo.py tests/test_repo.py
git commit -m "feat: sqlite storage with upsert dedup and filters"
```

---

## Task 8: Scheduler (`liza/scheduler.py`)

**Files:**
- Create: `liza/scheduler.py`
- Test: `tests/test_scheduler.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scheduler.py
import liza.scheduler as scheduler
from liza.models import ParsedVacancy
from liza.storage import repo


async def test_scrape_job_fetches_and_upserts(tmp_path, monkeypatch):
    repo.configure(str(tmp_path / "s.db"))
    repo.init_db()

    async def fake_fetch_all(keywords):
        return [ParsedVacancy(url="https://djinni.co/jobs/9/", title="Dev")]

    monkeypatch.setattr(scheduler, "fetch_all", fake_fetch_all)

    inserted, updated = await scheduler.scrape_job()
    assert (inserted, updated) == (1, 0)
    assert repo.list_vacancies()[1] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_scheduler.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'liza.scheduler'`

- [ ] **Step 3: Implement `liza/scheduler.py`**

```python
from __future__ import annotations

import logging
from typing import Optional, Tuple

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import settings
from .scraper.client import BlockedError
from .scraper.djinni import fetch_all
from .storage.repo import upsert_vacancies

logger = logging.getLogger("liza.scheduler")

_scheduler: Optional[AsyncIOScheduler] = None


async def scrape_job() -> Tuple[int, int]:
    try:
        parsed = await fetch_all(settings.keywords_list)
    except BlockedError as err:
        logger.warning("Scrape aborted (blocked): %s — consider setting DJINNI_COOKIE", err)
        return (0, 0)
    inserted, updated = upsert_vacancies(parsed)
    logger.info("Scrape done: %d new, %d updated", inserted, updated)
    return inserted, updated


def start_scheduler() -> None:
    global _scheduler
    if not settings.enable_scheduler:
        logger.info("Scheduler disabled (ENABLE_SCHEDULER=false)")
        return
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        scrape_job, "interval", minutes=settings.scrape_interval_min,
        id="djinni_scrape", max_instances=1, coalesce=True,
    )
    _scheduler.start()
    logger.info("Scheduler started: every %d min", settings.scrape_interval_min)


def shutdown_scheduler() -> None:
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_scheduler.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add liza/scheduler.py tests/test_scheduler.py
git commit -m "feat: apscheduler scrape job with block handling"
```

---

## Task 9: API (`liza/api/main.py`)

**Files:**
- Create: `liza/api/main.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api.py
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Disable the scheduler/startup scrape so the API never hits the network.
    monkeypatch.setenv("ENABLE_SCHEDULER", "false")
    monkeypatch.setenv("SCRAPE_ON_STARTUP", "false")

    from liza.config import settings
    settings.enable_scheduler = False
    settings.scrape_on_startup = False

    from liza.storage import repo
    repo.configure(str(tmp_path / "api.db"))
    repo.init_db()
    from liza.models import ParsedVacancy
    repo.upsert_vacancies([
        ParsedVacancy(url="u1", title="Senior Python Dev", category="Python",
                      work_format="remote", salary_max=6000),
        ParsedVacancy(url="u2", title="QA Manual", category="QA"),
    ])

    from liza.api.main import app
    with TestClient(app) as c:
        yield c


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_list_and_filter(client):
    body = client.get("/vacancies").json()
    assert body["total"] == 2

    body = client.get("/vacancies", params={"category": "Python"}).json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Senior Python Dev"


def test_get_one_and_404(client):
    listed = client.get("/vacancies").json()["items"]
    vid = listed[0]["id"]
    assert client.get(f"/vacancies/{vid}").status_code == 200
    assert client.get("/vacancies/999999").status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'liza.api.main'`

- [ ] **Step 3: Implement `liza/api/main.py`**

```python
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query

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


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/vacancies", response_model=VacancyList)
def list_vacancies(
    keyword: Optional[str] = None,
    category: Optional[str] = None,
    company: Optional[str] = None,
    remote: Optional[bool] = None,
    salary_min: Optional[int] = None,
    q: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> VacancyList:
    rows, total = repo.list_vacancies(
        keyword=keyword, category=category, company=company, remote=remote,
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_api.py -v`
Expected: 3 passed

- [ ] **Step 5: Run the whole suite**

Run: `.venv/bin/pytest -q -m "not network"`
Expected: all tests pass (config, models, parser, client, djinni, repo, scheduler, api).

- [ ] **Step 6: Commit**

```bash
git add liza/api/main.py tests/test_api.py
git commit -m "feat: fastapi endpoints with lifespan-managed scheduler"
```

---

## Task 10: Live smoke test, README, finalize

**Files:**
- Create: `tests/test_live.py` (network-gated), `README.md`

- [ ] **Step 1: Add a network-gated live integration test**

```python
# tests/test_live.py
import pytest

from liza.scraper.djinni import fetch_vacancies


@pytest.mark.network
async def test_live_fetch_returns_vacancies():
    vacancies = await fetch_vacancies(keyword="Python", max_pages=1)
    assert len(vacancies) > 0
    assert all(v.url for v in vacancies)
```

- [ ] **Step 2: Confirm it is skipped by default**

Run: `.venv/bin/pytest -q -m "not network"`
Expected: all unit tests pass; live test not run.

- [ ] **Step 3: Run the live test manually (one real page) to validate selectors**

Run: `.venv/bin/pytest tests/test_live.py -m network -v -s`
Expected: PASS if Djinni serves JSON-LD anonymously. If it raises `BlockedError`,
that is the documented anti-block risk — record it and set `DJINNI_COOKIE` in
`.env`, then re-run. @superpowers:verification-before-completion: report the
actual observed outcome here, do not assume.

- [ ] **Step 4: Write `README.md`**

Document: what LIZA does, install (`python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"`), config (`.env`), run the API (`.venv/bin/uvicorn liza.api.main:app --reload`), endpoints, how to run tests (`.venv/bin/pytest -m "not network"`), and the JSON-LD + anti-block notes from the spec.

- [ ] **Step 5: Manual smoke run of the API**

Run: `.venv/bin/uvicorn liza.api.main:app --port 8000` (with `SCRAPE_ON_STARTUP=true`),
then in another shell: `curl -s localhost:8000/vacancies | head` and
`curl -s localhost:8000/stats`. Confirm vacancies were scraped and served.
Record the observed counts.

- [ ] **Step 6: Commit**

```bash
git add tests/test_live.py README.md
git commit -m "feat: live smoke test (network-gated) and README"
```

---

## Done criteria

- `.venv/bin/pytest -m "not network"` is green.
- The live test (or manual smoke run) returns real vacancies, OR `BlockedError`
  is observed and the cookie workaround is documented.
- `uvicorn liza.api.main:app` serves `/vacancies`, `/vacancies/{id}`, `/scrape`,
  `/stats`, `/health`, and the scheduler refreshes on the configured interval.
