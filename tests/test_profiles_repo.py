from liza.models import CandidateProfile
from liza.storage import repo as store
from liza.profiles import repo as profiles


def test_create_get_list(tmp_path):
    store.configure(str(tmp_path / "p.db"))
    store.init_db()
    p = profiles.create_profile(CandidateProfile(slug="serhii", resume_md="cv"))
    assert p.id is not None
    assert profiles.get_profile(p.id).slug == "serhii"
    assert profiles.get_by_slug("serhii").id == p.id
    assert len(profiles.list_profiles()) == 1
