from liza.models import CandidateProfile, Vacancy
from liza.matching.prefilter import prefilter_reason


def _p(**kw):
    return CandidateProfile(slug="p", resume_md="cv", **kw)


def _v(**kw):
    kw.setdefault("title", "T")
    return Vacancy(url="u", first_seen=None, last_seen=None, **kw)


def test_keeps_normal_vacancy():
    assert prefilter_reason(_p(exclude_keywords_csv="gambling,casino"),
                            _v(title="Python Dev", description="fintech")) is None


def test_drops_on_excluded_keyword():
    reason = prefilter_reason(_p(exclude_keywords_csv="gambling,casino"),
                             _v(title="Casino Backend", description="igaming"))
    assert reason and "casino" in reason.lower()
