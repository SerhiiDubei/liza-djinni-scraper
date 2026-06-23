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


class _BelowScorer:
    model = "fake"
    async def score(self, profile, vacancy):
        from liza.jobhunter.contracts import MatchResult
        return MatchResult(score=50, verdict="consider", reasoning="meh")


class _ErrScorer:
    model = "fake"
    async def score(self, profile, vacancy):
        from liza.llm.client import LLMError
        raise LLMError("boom")


async def test_below_threshold_is_skipped(tmp_path):
    from datetime import date
    from liza.jobhunter.source import DbVacancySource
    from liza.models import CandidateProfile, ParsedVacancy
    from liza.storage import repo as store
    from liza.profiles import repo as profiles
    import liza.jobhunter.pipeline as pipeline
    store.configure(str(tmp_path / "b.db")); store.init_db()
    store.upsert_vacancies([ParsedVacancy(url="g", title="Dev", description="x",
                                          posted_date=date(2026, 6, 1))])
    profiles.create_profile(CandidateProfile(slug="s", resume_md="cv", min_score=70))
    res = await pipeline.run_match(profile_id=1, source=DbVacancySource(), scorer=_BelowScorer())
    assert res["scored"] == 1 and res["shortlisted"] == 0 and res["skipped"] == 1


async def test_llm_error_is_counted_and_swallowed(tmp_path):
    from datetime import date
    from liza.jobhunter.source import DbVacancySource
    from liza.models import CandidateProfile, ParsedVacancy
    from liza.storage import repo as store
    from liza.profiles import repo as profiles
    import liza.jobhunter.pipeline as pipeline
    store.configure(str(tmp_path / "e.db")); store.init_db()
    store.upsert_vacancies([ParsedVacancy(url="g", title="Dev", description="x",
                                          posted_date=date(2026, 6, 1))])
    profiles.create_profile(CandidateProfile(slug="s", resume_md="cv"))
    res = await pipeline.run_match(profile_id=1, source=DbVacancySource(), scorer=_ErrScorer())
    assert res["errors"] == 1 and res["scored"] == 0
