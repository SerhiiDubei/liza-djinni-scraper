import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ENABLE_SCHEDULER", "false")
    monkeypatch.setenv("SCRAPE_ON_STARTUP", "false")
    from liza.config import settings
    settings.enable_scheduler = False
    settings.scrape_on_startup = False
    from liza.storage import repo
    repo.configure(str(tmp_path / "api.db"))
    repo.init_db()
    from liza.api.main import app
    with TestClient(app) as c:
        yield c


def test_profile_crud_and_run(client, monkeypatch):
    r = client.post("/profiles", json={"slug": "serhii", "resume_md": "PM",
                                       "min_score": 70})
    assert r.status_code == 200
    pid = r.json()["id"]
    assert client.get(f"/profiles/{pid}").json()["slug"] == "serhii"

    import liza.jobhunter.pipeline as pipeline
    calls = {}
    def fake_trigger(profile_id, limit=None):
        calls["pid"] = profile_id
        return True
    monkeypatch.setattr(pipeline, "trigger_match", fake_trigger)
    body = client.post(f"/profiles/{pid}/run").json()
    assert body["status"] == "started" and calls["pid"] == pid


def test_candidacies_empty(client):
    r = client.post("/profiles", json={"slug": "x", "resume_md": "cv"})
    pid = r.json()["id"]
    body = client.get("/candidacies", params={"profile": pid}).json()
    assert body == {"items": [], "total": 0}
