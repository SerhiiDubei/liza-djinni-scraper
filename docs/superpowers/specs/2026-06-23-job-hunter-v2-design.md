# Job Hunter v2 — Design Spec

- **Date:** 2026-06-23
- **Status:** Draft (for approval)
- **Builds on:** LIZA (Djinni scraper + API + SQLite + dashboard)
- **Reuses:** craft/knowledge from `openclaw-workspace/skills/job-hunter` (pipeline, research protocol, cover-letter blocks, do-and-donts, examples)

## 1. Plain-language summary

LIZA already collects every vacancy. Job Hunter v2 adds the "brain" on top: for a given **candidate profile** (resume + preferences), a robot reads each vacancy by its actual responsibilities (not the title), scores the fit, keeps the ones above a threshold, researches the company, writes a tailored cover letter from reusable building blocks, and tracks the application funnel. The final "send" stays human-confirmed.

**Universal:** nothing is hardcoded to one person. Each user (me, my sister, a friend) is a separate `profile`. Everything is keyed by `profile_id`.

## 2. Goals / Non-goals

### Goals
- Per-profile, LLM-based **match scoring** of vacancies against a resume + hard preferences.
- A **threshold** that splits "worth applying" from "skip".
- **Enforced** company research (cannot be skipped) feeding cover letters.
- **Composable** cover letters (blocks combined per-vacancy, not one rigid template), grounded only in real resume data.
- **Funnel tracking** (shortlisted → researched → letter ready → applied → replied → interview → offer/rejected).
- **Multi-user** via profiles.
- Semi-automated **send** (human confirms the final click).

### Non-goals (v2)
- Fully automatic sending without human confirmation (unsafe: wrong target, CAPTCHA, account ban).
- Auto-creating accounts or bypassing bot-detection.
- Sources beyond Djinni (LIZA already abstracts the vacancy store; more sources later).

## 3. Decisions (approved)
- **Extend LIZA** — same repo, FastAPI service, SQLite DB, Railway deploy. Maximum reuse.
- **LLM via OpenRouter** — `OPENROUTER_API_KEY` as a Railway env var. Configurable model: a cheap model (e.g. `openai/gpt-4o-mini`) for scoring, a stronger model for cover writing.
- **Whole cycle designed at once**, implemented in phases (Section 9).

## 4. Architecture (new layer on LIZA)

```
liza/
├── profiles/          # candidate profiles (resume + preferences + voice)
│   └── repo.py        # CRUD; seed from files
├── llm/
│   └── client.py      # OpenRouter chat client: model, JSON mode, retries, BlockedError-style errors
├── matching/
│   ├── prefilter.py   # cheap rule filter (remote-only, exclude industries/keywords)
│   └── scorer.py      # LLM: read full vacancy → score + verdict + reasoning (structured)
├── research/
│   └── company.py     # ENFORCED multi-source company/product research → structured notes
├── cover/
│   ├── blocks.py      # block library + selection rules
│   └── composer.py    # LLM composes a letter from blocks (profile voice + research + match)
├── review/
│   └── checks.py      # quality gate: AI-slop, length, metrics-from-resume, language
├── pipeline.py        # orchestrator: prefilter → score → threshold → research → cover → review
└── api/ (extend main.py with the endpoints in §7)
```

### Data model (new tables, same SQLite DB)

**`candidate_profile`**
| field | notes |
|---|---|
| id / slug | e.g. `serhii`, `sister` |
| resume_md | full resume text |
| skills_md | detailed skills (optional) |
| preferences | JSON: `remote_only`, `exclude_industries[]` (e.g. gambling), `exclude_keywords[]`, `role_focus[]`, `min_score`, `language` (default `uk`) |
| voice_md | tone notes + feedback distilled from past letters |
| created/updated | |

**`candidacy`** — one row per (profile × vacancy), tracks the whole journey
| field | notes |
|---|---|
| id, profile_id, vacancy_id | FK to `vacancy`; unique(profile_id, vacancy_id) |
| score | 0–100 (or 1–10) |
| verdict | `apply` / `consider` / `skip` |
| reasoning | one-paragraph why |
| status | `scored` → `shortlisted` → `researching` → `research_done` → `letter_draft` → `letter_ready` → `applied` → `replied` → `interview` → `rejected` / `offer` |
| research_md | company/product notes (required before a letter) |
| cover_md | the cover letter |
| scored_at / applied_at / updated_at | |
| model | which LLM produced the score |

## 5. Pipeline (how a run works)

`run_pipeline(profile_id, limit?)`:
1. **Pre-filter** (cheap, no LLM): drop vacancies violating hard rules (not remote, excluded industry/keyword). Rules from `profile.preferences`.
2. **Score** (LLM, survivors only, only those not yet scored for this profile): feed the **full** vacancy (title + description/responsibilities + `raw_json`) and the profile resume/prefs → structured `{score, verdict, reasoning}`. Store a `candidacy`. *Title is ignored as the signal; responsibilities drive the score.*
3. **Threshold**: `score >= profile.min_score` → `status=shortlisted`; else `skip`.
4. **Research** (enforced): for each shortlisted, run `research_company` → `research_md`. Cover step refuses to run if research is missing.
5. **Cover** (LLM): `composer` builds a letter from blocks using profile voice + research + match reasoning → `cover_md`, `status=letter_draft`.
6. **Review**: quality checks; on pass → `letter_ready`.
7. **(Human) Send** → mark `applied` (Phase 3, §8).

**Cost control (important — catalog is ~8k):** pre-filter before any LLM call; score each (profile,vacancy) once and cache; re-run only scores new vacancies; per-run `limit`; cheap model for scoring. Log how many were scored/skipped.

## 6. Cover letters as blocks (not a stencil)

A **block library** (`cover/blocks.py`), each block a small instruction + examples:
- `match_summary` (required) — 2–3 concrete requirement↔experience bullets with real metrics.
- `hook` (required) — reflection from real experience, not empty praise.
- `deep_dive` (required) — `[what] → [result with numbers] → [relevance]`.
- `gap_address` (optional) — honest, transferable skills.
- `questions` (required, variable count 1–3) — simple, dialogue-opening.
- `cta` (required) — one sentence.
- `joke` / `greeting` / `product_praise` (optional flavor) — used sparingly.

The composer **selects and combines** blocks per vacancy (some optional ones in/out, order/wording varies) so letters are not cookie-cutter. Hard rules carried over from job-hunter: grounded in real resume data only (never invent metrics; if data missing → flag), default language `uk`, minimize company names in the body, no "AI-slop" phrases. Length target carried as a single config value (resolves the old 150-vs-400-word inconsistency — **one** source of truth).

## 7. API (extends LIZA FastAPI)

| Method | Path | Purpose |
|---|---|---|
| POST/GET | `/profiles`, `/profiles/{id}` | manage candidate profiles |
| POST | `/profiles/{id}/run` | run the pipeline (background); returns counts |
| GET | `/candidacies?profile=&status=&min_score=&limit=&offset=` | shortlist / funnel, sorted by score desc |
| GET | `/candidacies/{id}` | full detail (score, reasoning, research, cover) |
| POST | `/candidacies/{id}/research` | (re)run research |
| POST | `/candidacies/{id}/cover` | (re)generate cover from blocks |
| PATCH | `/candidacies/{id}` | status transitions (mark applied/replied/…); edit cover |

Dashboard (extend existing `/`): per-profile view — shortlist table with score, verdict, status; open a candidacy to see research + cover; buttons: regenerate cover, mark applied.

## 8. Send automation (Phase 3 — semi-auto)

- The server **cannot** click external apply forms. Sending is an **agent action** via the **Claude-in-Chrome** extension at runtime: open the vacancy apply URL → fill the cover field → **verify** company/role/URL match the candidacy → **stop and let the human click Send** (or explicit per-item confirmation).
- The app's role: provide the ready letter + apply URL + a verification checklist, and record the outcome (`status=applied`, `applied_at`). No unattended sending.
- Rationale: applying is irreversible and outward-facing; safety requires a human on the final click.

## 9. Implementation phases (build order)

1. **Profiles + matching** — profile model/CRUD, OpenRouter client, prefilter, LLM scorer, threshold, `candidacy` storage, `/profiles` + `/profiles/{id}/run` + `/candidacies`. Dashboard shortlist view. *(Delivers value fastest: a scored shortlist.)*
2. **Research + cover** — enforced research, block library + composer, review checks, candidacy detail + research/cover endpoints, dashboard detail view.
3. **Funnel + send** — status transitions, follow-up, Claude-in-Chrome semi-auto send with human confirm.

## 10. Reuse from `job-hunter`
- `research-protocol.md` → prompts/checklist for `research/company.py`.
- `cover-letter-template.md` + `dos-and-donts.md` → block definitions + composer guardrails.
- `examples/*` → few-shot examples for the composer.
- The user's `my-resume.md` / `my-profile.md` → seed **one** `candidate_profile` (as data, not hardcoded). (Note: keep PII out of any public repo.)

## 11. Testing (TDD)
- `prefilter` — rule filtering (remote-only, excludes) — pure, no LLM.
- `scorer` — parse/validate structured LLM output with a **mocked** LLM client; verdict/threshold logic.
- `research` enforcement — cover refuses without research.
- `composer` — block selection + grounding (mocked LLM); no invented metrics.
- `review/checks` — catches AI-slop / over-length / non-resume metrics.
- storage — candidacy upsert, unique(profile,vacancy), status transitions.
- API — endpoints over a seeded temp DB (mocked LLM); pipeline run counts.
- LLM and network are always mocked in the offline suite; a `network`-gated test may hit OpenRouter once.

## 12. Risks / open items
- **OpenRouter key** required as Railway env (`OPENROUTER_API_KEY`) — prerequisite for live scoring/cover.
- **LLM cost** on ~8k vacancies → mitigated by pre-filter + score-once + per-run limit + cheap model.
- **Research quality** depends on fetchable company info; if insufficient, flag rather than write shallow.
- **Send** depends on the Chrome extension being connected; otherwise stays manual.
- **PII**: profiles hold resumes — keep them in the DB/volume, never commit to a public repo.
