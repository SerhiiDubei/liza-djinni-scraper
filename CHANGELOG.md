# Changelog

- Auto-deploy from `main` to Railway enabled.
- Full-catalog backfill + hourly incremental refresh; per-page upsert.
- Vacancies sorted newest-first by `posted_date`.
- Async `/scrape` (background) with status in `/stats`.
- Static dashboard served at `/` (filters, pagination, scrape buttons).
- API timestamps emitted in explicit UTC (`+00:00`).
