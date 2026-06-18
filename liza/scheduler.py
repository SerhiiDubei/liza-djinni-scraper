from __future__ import annotations

import asyncio
import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import settings
from .scraper.client import BlockedError, ScrapeError
from .scraper.djinni import iter_pages
from .storage.repo import upsert_vacancies

logger = logging.getLogger("liza.scheduler")

_scheduler: Optional[AsyncIOScheduler] = None
_state = {"in_progress": False, "last_result": None}


def is_scraping() -> bool:
    return _state["in_progress"]


def scrape_status() -> dict:
    return {"in_progress": _state["in_progress"], "last_result": _state["last_result"]}


async def run_scrape(full: bool = False) -> dict:
    """Scrape the catalog and upsert PAGE BY PAGE so partial progress survives a block.

    full=True -> whole catalog (bounded only by settings.max_pages, usually None).
    full=False -> only settings.incremental_pages (routine refresh of newest pages).
    """
    if _state["in_progress"]:
        return {"skipped": True}
    _state["in_progress"] = True
    max_pages = None if full else settings.incremental_pages
    inserted = updated = pages = 0
    blocked = False
    try:
        keywords = settings.keywords_list or [None]
        for kw in keywords:
            try:
                async for page_vacs in iter_pages(kw, max_pages):
                    i, u = upsert_vacancies(page_vacs)
                    inserted += i
                    updated += u
                    pages += 1
            except BlockedError as err:
                blocked = True
                logger.warning("Scrape blocked: %s — consider setting DJINNI_COOKIE", err)
                break
            except ScrapeError as err:
                logger.warning("Scrape failed (transient): %s", err)
                break
        result = {"inserted": inserted, "updated": updated, "pages": pages,
                  "blocked": blocked, "full": full}
        _state["last_result"] = result
        logger.info("Scrape done: %s", result)
        return result
    finally:
        _state["in_progress"] = False


def trigger_scrape(full: bool = False) -> bool:
    """Fire-and-forget a scrape. Returns False if one is already running."""
    if _state["in_progress"]:
        return False
    asyncio.create_task(run_scrape(full))
    return True


def start_scheduler() -> None:
    global _scheduler
    if not settings.enable_scheduler:
        logger.info("Scheduler disabled (ENABLE_SCHEDULER=false)")
        return
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        run_scrape, "interval", minutes=settings.scrape_interval_min,
        kwargs={"full": False}, id="djinni_scrape", max_instances=1, coalesce=True,
    )
    _scheduler.start()
    logger.info("Scheduler started: every %d min", settings.scrape_interval_min)


def shutdown_scheduler() -> None:
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
