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
        else:
            types = data.get("@type")
            if types == "JobPosting" or (
                isinstance(types, list) and "JobPosting" in types
            ):
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
        locality = addr.get("addressLocality")
        if isinstance(locality, list):
            locality = locality[0] if locality else None
        parts = [locality, addr.get("addressCountry")]
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
