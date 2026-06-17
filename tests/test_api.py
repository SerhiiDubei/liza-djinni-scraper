import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Disable the scheduler/startup scrape so the API never hits the network.
    monkeypatch.setenv("ENABLE_SCHEDULER", "false")
    monkeypatch.setenv("SCRAPE_ON_STARTUP", "false")

    from liza.config import settings
    settings.enable_scheduler = False
    settings.scrape_on_startup = False

    from liza.storage import repo
    repo.configure(str(tmp_path / "api.db"))
    repo.init_db()
    from liza.models import ParsedVacancy
    repo.upsert_vacancies([
        ParsedVacancy(url="u1", title="Senior Python Dev", category="Python",
                      work_format="remote", salary_max=6000),
        ParsedVacancy(url="u2", title="QA Manual", category="QA"),
    ])

    from liza.api.main import app
    with TestClient(app) as c:
        yield c


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_list_and_filter(client):
    body = client.get("/vacancies").json()
    assert body["total"] == 2

    body = client.get("/vacancies", params={"category": "Python"}).json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Senior Python Dev"


def test_get_one_and_404(client):
    listed = client.get("/vacancies").json()["items"]
    vid = listed[0]["id"]
    assert client.get(f"/vacancies/{vid}").status_code == 200
    assert client.get("/vacancies/999999").status_code == 404
