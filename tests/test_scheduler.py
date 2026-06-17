import liza.scheduler as scheduler
from liza.models import ParsedVacancy
from liza.storage import repo


async def test_scrape_job_fetches_and_upserts(tmp_path, monkeypatch):
    repo.configure(str(tmp_path / "s.db"))
    repo.init_db()

    async def fake_fetch_all(keywords):
        return [ParsedVacancy(url="https://djinni.co/jobs/9/", title="Dev")]

    monkeypatch.setattr(scheduler, "fetch_all", fake_fetch_all)

    inserted, updated = await scheduler.scrape_job()
    assert (inserted, updated) == (1, 0)
    assert repo.list_vacancies()[1] == 1
