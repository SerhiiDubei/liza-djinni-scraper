from __future__ import annotations

from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    djinni_base_url: str = "https://djinni.co"
    scrape_interval_min: int = 60
    djinni_keywords: str = ""           # CSV; empty = all categories
    max_pages: Optional[int] = None     # safety cap; None = until last page
    request_delay_sec: float = 2.0
    db_path: str = "./liza.db"
    djinni_cookie: str = ""             # optional sessionid; empty = anonymous
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    enable_scheduler: bool = True
    scrape_on_startup: bool = True

    @property
    def keywords_list(self) -> List[str]:
        return [k.strip() for k in self.djinni_keywords.split(",") if k.strip()]


settings = Settings()
