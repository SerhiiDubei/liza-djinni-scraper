from __future__ import annotations

import asyncio
import json
import re
from typing import Optional

import httpx

from ..config import settings


class LLMError(Exception):
    """LLM call failed or returned unparseable output."""


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class LLMClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: int = 3,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.api_key = settings.openrouter_api_key if api_key is None else api_key
        self.model = model or settings.llm_model_score
        self.max_retries = max_retries
        self.last_usage: dict = {}
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.openrouter_base_url,
            timeout=settings.llm_timeout_sec if timeout is None else timeout,
            transport=transport,
        )

    async def __aenter__(self) -> "LLMClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self._client.aclose()

    async def complete_json(self, system: str, user: str, model: Optional[str] = None) -> dict:
        if not self.api_key:
            raise LLMError("OPENROUTER_API_KEY is not set")
        payload = {
            "model": model or self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": "Bearer " + self.api_key,
                   "Content-Type": "application/json"}
        last: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                r = await self._client.post("/chat/completions", json=payload, headers=headers)
            except httpx.HTTPError as err:
                last = err
                if attempt < self.max_retries:
                    await asyncio.sleep(0.5 * attempt)
                continue
            if r.status_code in (429, 500, 502, 503):
                last = LLMError("HTTP " + str(r.status_code))
                if attempt < self.max_retries:
                    await asyncio.sleep(0.5 * attempt)
                continue
            r.raise_for_status()
            data = r.json()
            self.last_usage = data.get("usage") or {}
            content = data["choices"][0]["message"]["content"].strip()
            content = _FENCE.sub("", content).strip()
            try:
                return json.loads(content)
            except (ValueError, TypeError) as err:
                raise LLMError("Bad JSON from LLM: " + str(err))
        raise LLMError("LLM call failed after retries: " + str(last))
