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


def test_include_keywords_keep_and_drop():
    from liza.matching.prefilter import prefilter_reason
    from liza.models import CandidateProfile, Vacancy
    p = CandidateProfile(slug="p", resume_md="cv", include_keywords_csv="product,marketing,growth")
    v_keep = Vacancy(url="u", title="Senior Product Manager", first_seen=None, last_seen=None)
    v_drop = Vacancy(url="u2", title="Backend Developer", first_seen=None, last_seen=None)
    assert prefilter_reason(p, v_keep) is None
    assert prefilter_reason(p, v_drop) == "off-target role"
