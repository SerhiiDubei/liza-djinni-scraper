from datetime import date

import liza.jobhunter.pipeline as pipeline
from liza.jobhunter.contracts import MatchResult
from liza.jobhunter.source import DbVacancySource
from liza.models import CandidateProfile, ParsedVacancy
from liza.storage import repo as store
from liza.profiles import repo as profiles
from liza.jobhunter import repo as jh


class FakeScorer:
    model = "fake"

    async def score(self, profile, vacancy):
        return MatchResult(score=88, verdict="apply", reasoning="fit")


async def test_run_match_scores_and_thresholds(tmp_path):
    store.configure(str(tmp_path / "m.db"))
    store.init_db()
    store.upsert_vacancies([
        ParsedVacancy(url="good", title="Growth PM", description="own roadmap",
                      posted_date=date(2026, 6, 2)),
        ParsedVacancy(url="bad", title="Casino Dev", description="igaming",
                      posted_date=date(2026, 6, 1)),
    ])
    profiles.create_profile(CandidateProfile(
        slug="serhii", resume_md="PM", min_score=70, exclude_keywords_csv="casino"))

    res = await pipeline.run_match(profile_id=1, limit=10,
                                   source=DbVacancySource(), scorer=FakeScorer())
    assert res["scored"] == 2        # 1 prefiltered + 1 LLM-scored
    assert res["shortlisted"] == 1
    assert res["skipped"] == 1

    short, n = jh.list_candidacies(profile_id=1, status="shortlisted")
    assert n == 1 and short[0].title == "Growth PM" and short[0].score == 88
