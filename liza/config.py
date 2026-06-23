from __future__ import annotations

import os
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


def _normalized_env(name: str, environ: Optional[dict] = None) -> str:
    """Read an env var tolerantly.

    Matches even if the STORED variable name has stray surrounding whitespace or
    newlines (a common copy-paste error in hosting dashboards, where the UI hides
    the stray char but the process env keeps it, e.g. ``OPENROUTER_API_KEY\\n``).
    Returns the stripped value, or '' if not found.
    """
    environ = os.environ if environ is None else environ
    direct = environ.get(name)
    if direct and direct.strip():
        return direct.strip()
    target = name.strip().upper()
    for key, value in environ.items():
        if key.strip().upper() == target and value and value.strip():
            return value.strip()
    return ""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    djinni_base_url: str = "https://djinni.co"
    scrape_interval_min: int = 60
    djinni_keywords: str = ""           # CSV; empty = all categories
    max_pages: Optional[int] = None     # safety cap; None = until last page
    incremental_pages: int = 3   # pages scraped on routine/incremental refresh
    request_delay_sec: float = 2.0
    db_path: str = "./liza.db"
    djinni_cookie: str = ""             # optional sessionid; empty = anonymous
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    enable_scheduler: bool = True
    scrape_on_startup: bool = True

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_model_score: str = "openai/gpt-4o-mini"
    llm_timeout_sec: float = 60.0
    match_default_limit: int = 50   # vacancies scored per run by default

    @property
    def keywords_list(self) -> List[str]:
        return [k.strip() for k in self.djinni_keywords.split(",") if k.strip()]


settings = Settings()

# Defensive: tolerate a malformed OPENROUTER_API_KEY env var NAME (stray
# whitespace/newline from dashboard paste) that pydantic-settings would miss.
if not settings.openrouter_api_key:
    settings.openrouter_api_key = _normalized_env("OPENROUTER_API_KEY")
