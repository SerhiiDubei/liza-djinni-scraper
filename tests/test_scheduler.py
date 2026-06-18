import httpx
import pytest

import liza.scheduler as scheduler
from liza.config import settings
from liza.scraper import djinni
from liza.storage import repo

PAGE_OK = (
    '<html><head><script type="application/ld+json">'
    '{"@type":"JobPosting","title":"J1","url":"https://djinni.co/jobs/1/"}'
    '</script></head><body><a href="?page=1">1</a><a href="?page=2">2</a></body></html>'
)


def _block_on_page2_transport():
    def handler(req):
        page = int(req.url.params.get("page", "1"))
        if page == 1:
            return httpx.Response(200, text=PAGE_OK)
        return httpx.Response(429, text="blocked")
    return httpx.MockTransport(handler)


async def test_run_scrape_persists_each_page_and_survives_block(tmp_path, monkeypatch):
    repo.configure(str(tmp_path / "s.db"))
    repo.init_db()
    monkeypatch.setattr(settings, "request_delay_sec", 0)

    transport = _block_on_page2_transport()

    def patched_iter(keyword=None, max_pages=None, transport=None):
        return djinni.iter_pages(keyword=keyword, max_pages=max_pages, transport=transport)

    # Inject the mock transport by wrapping iter_pages used inside scheduler.
    real_iter = djinni.iter_pages

    def iter_with_transport(keyword=None, max_pages=None):
        return real_iter(keyword=keyword, max_pages=max_pages, transport=transport)

    monkeypatch.setattr(scheduler, "iter_pages", iter_with_transport)

    res = await scheduler.run_scrape(full=True)
    assert res["blocked"] is True
    assert res["inserted"] == 1          # page 1 persisted BEFORE the block
    assert repo.list_vacancies()[1] == 1


async def test_run_scrape_skips_when_already_in_progress(monkeypatch):
    scheduler._state["in_progress"] = True
    try:
        res = await scheduler.run_scrape()
        assert res == {"skipped": True}
        assert scheduler.trigger_scrape() is False
    finally:
        scheduler._state["in_progress"] = False
