import pytest

from liza.scraper.djinni import fetch_vacancies


@pytest.mark.network
async def test_live_fetch_returns_vacancies():
    vacancies = await fetch_vacancies(keyword="Python", max_pages=1)
    assert len(vacancies) > 0
    assert all(v.url for v in vacancies)
