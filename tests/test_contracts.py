from liza.models import CandidateProfile, Vacancy
from liza.jobhunter.contracts import MatchResult
from liza.matching.scorer import LlmScorer


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload
        self.model = "fake-model"

    async def complete_json(self, system, user):
        return self.payload


async def test_llmscorer_returns_matchresult_clamped():
    scorer = LlmScorer(FakeLLM({"score": 150, "verdict": "apply", "reasoning": "x"}))
    p = CandidateProfile(slug="p", resume_md="cv")
    v = Vacancy(url="u", title="T", first_seen=None, last_seen=None)
    r = await scorer.score(p, v)
    assert isinstance(r, MatchResult)
    assert r.score == 100 and r.verdict == "apply"
    assert scorer.model == "fake-model"
