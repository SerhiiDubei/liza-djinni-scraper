from liza.models import CandidateProfile, Vacancy
from liza.matching.scorer import build_prompt, normalize_score


def test_normalize_clamps_and_defaults():
    assert normalize_score({"score": 150, "verdict": "apply"})["score"] == 100
    assert normalize_score({"score": -5, "verdict": "x"})["score"] == 0
    out = normalize_score({"score": 80, "verdict": "weird", "reasoning": "ok"})
    assert out["verdict"] == "skip"     # unknown verdict -> skip
    assert out["reasoning"] == "ok"


def test_build_prompt_includes_resume_and_vacancy():
    p = CandidateProfile(slug="p", resume_md="MY-RESUME", role_focus="PM")
    v = Vacancy(url="u", title="Growth PM", description="own roadmap",
                first_seen=None, last_seen=None)
    system, user = build_prompt(p, v)
    assert "MY-RESUME" in user and "Growth PM" in user
    assert "JSON" in system.upper()
