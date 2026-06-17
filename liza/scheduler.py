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
