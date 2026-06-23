from liza.models import CandidateProfile, Candidacy


def test_profile_defaults():
    p = CandidateProfile(slug="serhii", resume_md="CV")
    assert p.min_score == 70
    assert p.remote_only is True
    assert p.language == "uk"


def test_candidacy_is_table():
    assert Candidacy.__tablename__ == "candidacy"
