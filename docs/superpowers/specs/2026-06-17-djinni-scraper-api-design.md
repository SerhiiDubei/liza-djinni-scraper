# LIZA — Djinni Vacancies Scraper + API — Design Spec

- **Date:** 2026-06-17
- **Status:** Approved (design)
- **Owner:** Serhii Dubei

## 1. Purpose

A self-hosted Python service that periodically scrapes job vacancies from the
public Djinni catalog (`https://djinni.co/jobs/`), stores them in a local
database with deduplication, and exposes them through an HTTP API.

Djinni has **no public read API** for vacancies; its partner API is for
employers (posting jobs / receiving candidates). Scraping the public catalog is
therefore the only way to *obtain* the vacancy feed.

## 2. Goals & Non-Goals

### Goals (v1)
- Scrape the public Djinni jobs listing on a schedule (default hourly).
- Parse vacancies via **Schema.org JSON-LD** (`JobPosting`) — durable against
  layout/CSS changes.
- Persist to **SQLite** with dedup keyed on the vacancy URL; track
  `first_seen` / `last_seen`.
- Serve vacancies via a **FastAPI** HTTP API with filtering and pagination.
- Be a polite, anonymous scraper (realistic User-Agent, inter-request delay,
  exponential backoff, block detection).

### Non-Goals (deferred to later versions)
- Deployment (Railway), Postgres backend.
- Detail-page scraping (English level, experience, full description, views).
- Notifications (Telegram/Slack/email).
- Authenticated scraping with a `sessionid` cookie (config hook exists, but the
  default path is anonymous).

## 3. Decisions (from brainstorming)

| Decision | Choice | Rationale |
|---|---|---|
| Output | HTTP API service | User goal: serve vacancies to other apps. |
| Language | Python | Largest pool of reference scrapers; fits FastAPI. |
| Base technique | JSON-LD parsing, adapted from `analisto/djinni_co` | JSON-LD is SEO-driven and stable; the cleanest, most durable approach found across 8 evaluated repos. |
| Reuse model | Adapt the technique, write our own code | **No evaluated repo has a license** (all-rights-reserved). We adopt the proven JSON-LD approach and write clean, owned code to avoid the licensing gray area. |
| Storage | SQLite | Zero infra; migratable to Postgres later. |
| Scope/filters | Fully optional, config-driven | User undecided on scope → default = all categories, optional keyword/category filters. |
| Run mode | Scheduled (APScheduler, in-process) + manual trigger | User wants scheduled runs; manual endpoint aids testing. |
| Anti-block | Anonymous + polite | Start without login; add cookie only if blocked. |

### Repo evaluation summary (8 candidates)
- ⭐ `analisto/djinni_co` — aiohttp+bs4, **JSON-LD**, recent (2026-02), clean
  importable `parse_listing_page()`, quality 4/5. Needs sessionid cookie; no
  license. **Chosen as the technique reference.**
- `sqanatoliy/djinni_scraper` — Scrapy+Playwright, login-centric, SQLite+Telegram
  coupled, heavy. Reference only.
- `ArtemLeo/...`, `olgierrd/...` — brittle 2024 CSS selectors, 2–3 fields. Skip.
- `AbsoluteAnchor/...`, `BlackFalconData/...` — README-only marketing for paid
  Apify actors. Skip.
- `TatianaKalina/...`, `barabarinov/...` — empty stub repos. Skip.

## 4. Architecture

```
liza/
├── pyproject.toml          # fastapi, uvicorn, httpx, beautifulsoup4, lxml,
│                           # sqlmodel, apscheduler, pydantic-settings, pytest
├── .env.example
├── README.md
├── liza/
│   ├── config.py           # Settings via pydantic-settings (env-driven)
│   ├── models.py           # Vacancy table + Pydantic response schemas
│   ├── scraper/
│   │   ├── client.py       # httpx async client: UA, delay, backoff, block detect
│   │   ├── parser.py       # JSON-LD JobPosting -> Vacancy (pure, no I/O)  ← core
│   │   └── djinni.py       # fetch_vacancies(filters) -> list[Vacancy]; pagination
│   ├── storage/repo.py     # SQLite engine; upsert (dedup by url); filtered queries
│   ├── scheduler.py        # APScheduler job: scrape -> upsert
│   └── api/main.py         # FastAPI app + lifespan starts/stops scheduler
└── tests/
    ├── test_parser.py
    ├── test_repo.py
    └── fixtures/djinni_jobs.html
```

### Component responsibilities

- **config.py** — `Settings` from env: `base_url`, `scrape_interval_min`,
  `keywords`, `max_pages`, `request_delay_sec`, `db_path`, `user_agent`,
  `djinni_cookie` (optional). Single source of configuration.
- **scraper/parser.py** — `parse_jobs_page(html: str) -> tuple[list[Vacancy], int]`.
  Extracts JSON-LD `JobPosting` objects, returns vacancies + total pages.
  Pure function, no network/DB. The durable core; unit-tested against a fixture.
- **scraper/client.py** — async httpx wrapper: realistic User-Agent, configurable
  delay, exponential backoff on 429/5xx, raises a typed `BlockedError` on
  403/429-after-retries, optional cookie injection.
- **scraper/djinni.py** — `async fetch_vacancies(filters) -> list[Vacancy]`:
  builds the URL (`/jobs/?primary_keyword=...&page=N`), loops pages via the
  client, calls the parser, stops at last page / `max_pages`. No DB.
- **storage/repo.py** — `upsert_vacancies(records)` (dedup by `url`; set
  `first_seen` once, always update `last_seen`), `list_vacancies(filters, limit,
  offset) -> (items, total)`, `get_vacancy(id)`. SQLite via SQLModel.
- **scheduler.py** — APScheduler `AsyncIOScheduler` running
  `fetch_vacancies -> upsert_vacancies` every `scrape_interval_min`; also runs
  once on startup. Logs inserted/updated counts.
- **api/main.py** — FastAPI with a lifespan that starts/stops the scheduler.

## 5. Data Model — `Vacancy`

| Field | Type | Notes |
|---|---|---|
| `id` | int, PK | autoincrement |
| `url` | str, unique | natural key for dedup |
| `title` | str | |
| `company` | str \| null | JSON-LD `hiringOrganization.name` |
| `salary_min` | int \| null | JSON-LD `baseSalary` |
| `salary_max` | int \| null | |
| `salary_currency` | str \| null | |
| `category` | str \| null | primary keyword used / inferred |
| `work_format` | str \| null | remote / office / hybrid (from `jobLocationType`/`employmentType` where available) |
| `location` | str \| null | city/country text |
| `posted_date` | date \| null | JSON-LD `datePosted` |
| `description` | str \| null | short, from JSON-LD `description` |
| `first_seen` | datetime | set on first insert |
| `last_seen` | datetime | updated every time the vacancy is seen |
| `raw_json` | str \| null | the raw JSON-LD blob, for future field extraction |

> Available fields are bounded by what JSON-LD exposes on listing pages
> (`title`, `hiringOrganization`, `datePosted`, `validThrough`, `employmentType`,
> `jobLocation`, `baseSalary`, `description`, `url`). Djinni-specific fields
> (english level, experience years, views) live on detail pages → v2.

## 6. Data Flow

```
APScheduler tick (every scrape_interval_min, + once at startup)
  → fetch_vacancies(filters)            scraper/djinni.py
      → client.get(?page=N)             scraper/client.py  (UA, delay, backoff)
      → parse_jobs_page(html)           scraper/parser.py  (JSON-LD)
  → upsert_vacancies(records)           storage/repo.py    (dedup by url)
SQLite ⇄ FastAPI  GET /vacancies         api/main.py
```

## 7. HTTP API

| Method | Path | Description |
|---|---|---|
| GET | `/health` | liveness |
| GET | `/vacancies` | filters: `keyword`, `category`, `company`, `remote`, `salary_min`, `q` (title contains), `limit` (default 50, max 200), `offset`; returns `{items: [...], total: N}` |
| GET | `/vacancies/{id}` | single vacancy or 404 |
| POST | `/scrape` | trigger a scrape now; returns `{inserted, updated}` |
| GET | `/stats` | counts (total, by category, last scrape time) |

## 8. Error Handling

- **HTTP/network errors** → retry with exponential backoff in `client.py`;
  after N retries, log and skip the page, continue with the rest.
- **Block detection (403/429)** → raise `BlockedError`; the scheduler job
  catches it, logs a warning (signal to enable the cookie), and ends the run.
  Existing data is preserved; the next tick retries.
- **No JSON-LD on a page** → treat as end-of-results; no crash.
- **Upserts are idempotent** → partial/failed runs are safe to re-run.

## 9. Configuration (`.env`)

```
DJINNI_BASE_URL=https://djinni.co
SCRAPE_INTERVAL_MIN=60
DJINNI_KEYWORDS=            # empty = all categories; CSV e.g. Python,JavaScript
MAX_PAGES=                  # safety cap; empty = until last page
REQUEST_DELAY_SEC=2.0
USER_AGENT=Mozilla/5.0 (...)  # realistic desktop UA
DB_PATH=./liza.db
DJINNI_COOKIE=              # optional sessionid; empty = anonymous
```

## 10. Testing (TDD)

1. **`test_parser.py` (write first)** — saved real Djinni jobs HTML fixture;
   assert the parser returns ≥1 vacancy with expected fields and the correct
   total-page count. Drives the parser implementation.
2. **`test_repo.py`** — upsert the same URL twice → exactly one row, `last_seen`
   advanced, `first_seen` unchanged; filtered queries return expected subsets.
3. **`test_api.py`** (optional) — FastAPI `TestClient` over a seeded temp DB.
4. **Live integration test** — gated behind a `network` marker; skipped by
   default to keep the suite offline and deterministic.

## 11. Build Sequence

1. `pyproject.toml`, package skeleton, `config.py`.
2. `models.py` (`Vacancy` + schemas).
3. `test_parser.py` + fixture → `scraper/parser.py` (TDD).
4. `scraper/client.py`, then `scraper/djinni.py`.
5. `test_repo.py` → `storage/repo.py`.
6. `scheduler.py`.
7. `api/main.py` wiring + lifespan.
8. `README.md`, `.env.example`, manual smoke run.

## 12. Risks

- **IP blocking** without a session is the main operational risk. Mitigation:
  polite delays + backoff + block detection; optional cookie hook ready.
- **JSON-LD shape drift** — mitigated by storing `raw_json` and defensive parsing.
- **Legal/ToS** — scraping may conflict with Djinni ToS; this is a personal
  tool; we own all code and only read public pages politely.
