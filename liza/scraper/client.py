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
