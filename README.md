# LIZA — Djinni Vacancies Scraper & API

LIZA is a self-hosted Python service that scrapes the public [Djinni](https://djinni.co) jobs catalog via Schema.org JSON-LD markup on a schedule, stores vacancies in SQLite with deduplication, and serves them over a FastAPI HTTP API.

**Live:** dashboard + API at https://liza-production-8548.up.railway.app/ (deployed on Railway, auto-deploys on push to `main`).

> **Note:** There is no official public Djinni read API. LIZA scrapes public pages. Respect Djinni's Terms of Service and keep request rates polite.

---

## Features

- Parses `JobPosting` JSON-LD embedded in every Djinni jobs page — durable, no fragile CSS selectors.
- Periodic background refresh via APScheduler.
- SQLite storage with URL-based dedup (`first_seen` / `last_seen` timestamps).
- FastAPI REST API with filtering, full-text search, and pagination.
- Polite delays, exponential backoff, and block detection.

---

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

---

## Configuration

Copy the example env file and edit as needed:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `DJINNI_BASE_URL` | `https://djinni.co` | Base URL for the Djinni site |
| `SCRAPE_INTERVAL_MIN` | `60` | Minutes between scheduled scrapes |
| `DJINNI_KEYWORDS` | `` (empty) | Comma-separated keywords to scrape; empty = all categories |
| `MAX_PAGES` | `` (empty = unlimited) | Safety cap on pages fetched per keyword |
| `REQUEST_DELAY_SEC` | `2.0` | Seconds to wait between HTTP requests (polite crawling) |
| `DB_PATH` | `./liza.db` | Path to the SQLite database file |
| `DJINNI_COOKIE` | `` (empty) | Optional `sessionid` cookie for a logged-in Djinni account; set this if anonymous requests are blocked |
| `ENABLE_SCHEDULER` | `true` | Enable/disable the periodic background scraper |
| `SCRAPE_ON_STARTUP` | `true` | Run a scrape immediately when the API starts |

---

## Run the API

```bash
.venv/bin/uvicorn liza.api.main:app --reload
```

The API starts on `http://localhost:8000` by default.

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Returns `{"status": "ok"}` |
| `GET` | `/vacancies` | List vacancies with optional filters (see below) |
| `GET` | `/vacancies/{id}` | Fetch a single vacancy by integer ID |
| `POST` | `/scrape` | Trigger an immediate scrape; returns `{"inserted": N, "updated": M}` |
| `GET` | `/stats` | Returns total count, breakdown by category, and last scrape time |

### `/vacancies` query parameters

| Parameter | Type | Description |
|---|---|---|
| `category` | string | Filter by category field (exact match) |
| `company` | string | Filter by company name (exact match) |
| `remote` | bool | Filter by remote work format |
| `salary_min` | int | Returns vacancies whose stated maximum salary is ≥ this value; vacancies without a stated salary are excluded |
| `q` | string | Case-insensitive title search (contains match) |
| `limit` | int | Page size (default 50, max 200) |
| `offset` | int | Pagination offset (default 0) |

---

## Job Hunter (matching)

LIZA includes a **Phase 1** job-hunter pipeline that scores scraped vacancies against a candidate profile using an LLM and builds a ranked shortlist.

### What it does

1. For each profile, fetches all unscored vacancies from the database.
2. Applies a fast keyword prefilter to skip obviously irrelevant postings without calling the LLM.
3. Sends each remaining vacancy to an OpenRouter LLM (default: `gpt-4o-mini`) with the profile's requirements and the vacancy text; receives a numeric score (0–100), a verdict (`apply` / `consider` / `skip`), and a short reasoning.
4. Persists results in the `candidacies` table — each vacancy is scored at most once per profile (`score-once` guarantee).
5. A **threshold** (`min_score` on the profile) determines the candidacy **status**: `shortlisted` (score ≥ threshold) or `skipped` (score < threshold).

This is Phase 1 of a larger pipeline; research, cover-letter generation, and a full application funnel are planned for later phases.

### Required env variables

| Variable | Description |
|---|---|
| `OPENROUTER_API_KEY` | API key from [openrouter.ai/keys](https://openrouter.ai/keys) |
| `LLM_MODEL_SCORE` | OpenRouter model ID used for scoring (default: `openai/gpt-4o-mini`) |

### Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/profiles` | Create a new candidate profile |
| `GET` | `/profiles` | List all profiles |
| `GET` | `/profiles/{id}` | Fetch a single profile by ID |
| `POST` | `/profiles/{id}/run` | Trigger LLM matching for a profile (async, returns immediately) |
| `GET` | `/candidacies` | List candidacies; supports `?profile=`, `?status=`, `?min_score=` |

The dashboard at `/` includes a **Job Hunter — Shortlist** tab where you can trigger a match run and browse shortlisted results directly in the browser.

---

## Run Tests

**Offline unit tests** (no network required):

```bash
.venv/bin/pytest -m "not network"
```

Expected: all offline tests pass.

**Live integration test** (hits the real Djinni site):

```bash
.venv/bin/pytest -m network -v -s
```

This fetches one real page from `https://djinni.co/jobs/?primary_keyword=Python` and asserts vacancies are returned. Requires a working internet connection and ~5 seconds (due to the polite 2 s request delay).

---

## How It Works

1. **JSON-LD parsing** — Djinni embeds `<script type="application/ld+json">` blocks with `JobPosting` Schema.org data on every jobs page. LIZA extracts these with BeautifulSoup and parses them as structured data — no brittle CSS class scraping.

2. **APScheduler periodic refresh** — A background `AsyncIOScheduler` runs `scrape_job()` every `SCRAPE_INTERVAL_MIN` minutes. Calling `POST /scrape` triggers the same job on demand.

3. **SQLite dedup by URL** — Each vacancy is identified by its canonical URL. On every scrape, existing rows are updated (`last_seen`, salary, etc.) and new URLs are inserted. `first_seen` is never overwritten.

---

## Known Limitations & Anti-Block

Djinni may rate-limit or block anonymous scraping after several rapid requests. LIZA mitigates this with:

- A configurable `REQUEST_DELAY_SEC` (default 2.0 s) between requests.
- Exponential backoff on HTTP errors.
- `BlockedError` detection — when a page returns a CAPTCHA / login wall, the scraper logs a warning and stops the current run cleanly.

**Live test result (2026-06-17, anonymous, one page):** The request reached Djinni successfully and returned **15 Python vacancies** (e.g. "Senior Software Engineer (AdTech)" at Sigma Software, "Senior Backend (Python) Engineer" at Adaptiq). No block was triggered.

**If you are blocked:** Set `DJINNI_COOKIE` in `.env` to the `sessionid` cookie value from a logged-in Djinni session. Anonymous scraping at polite rates generally works, but a logged-in session is more resilient.

---

## Project Structure

```
liza/
  config.py        — pydantic-settings env config
  models.py        — ParsedVacancy, VacancyRow, VacancyRead, VacancyList
  scraper/
    client.py      — async httpx client with delay, backoff, block detection
    parser.py      — JSON-LD JobPosting extractor
    djinni.py      — fetch_vacancies() / fetch_all() orchestration
  storage/
    repo.py        — SQLite upsert, list, stats via SQLModel
  scheduler.py     — APScheduler integration
  api/
    main.py        — FastAPI app with lifespan
tests/
  test_parser.py   — offline parser unit tests (fixture HTML)
  test_djinni.py   — scraper unit tests (transport mock)
  test_repo.py     — storage unit tests (in-memory SQLite)
  test_api.py      — API endpoint tests (TestClient)
  test_live.py     — @pytest.mark.network live test (skipped by default)
  ...
```
