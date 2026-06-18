from __future__ import annotations

from typing import AsyncIterator, Dict, List, Optional

import httpx

from ..config import settings
from ..models import ParsedVacancy
from .client import DjinniClient
from .parser import parse_jobs_page


async def iter_pages(
    keyword: Optional[str] = None,
    max_pages: Optional[int] = None,
    transport: Optional[httpx.BaseTransport] = None,
) -> AsyncIterator[List[ParsedVacancy]]:
    """Yield one list of ParsedVacancy per catalog page until exhausted/capped.

    Raises BlockedError/ScrapeError from the client on failure (caller handles).
    """
    cap = max_pages if max_pages is not None else settings.max_pages
    async with DjinniClient(transport=transport) as client:
        page = 1
        while True:
            params: Dict[str, object] = {"page": page}
            if keyword:
                params["primary_keyword"] = keyword
            html = await client.get("/jobs/", params=params)
            vacancies, total_pages = parse_jobs_page(html)
            if not vacancies:
                return
            if keyword:
                for v in vacancies:
                    if not v.category:
                        v.category = keyword
            yield vacancies
            limit = min(cap, total_pages) if cap else total_pages
            if page >= limit:
                return
            page += 1


async def fetch_vacancies(
    keyword: Optional[str] = None,
    max_pages: Optional[int] = None,
    transport: Optional[httpx.BaseTransport] = None,
) -> List[ParsedVacancy]:
    results: Dict[str, ParsedVacancy] = {}
    async for page_vacs in iter_pages(keyword, max_pages, transport):
        for v in page_vacs:
            if v.url:
                results[v.url] = v
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
