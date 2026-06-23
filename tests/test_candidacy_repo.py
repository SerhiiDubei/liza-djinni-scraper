from datetime import date
from liza.models import Candidacy, ParsedVacancy
from liza.storage import repo as store
from liza.jobhunter import repo as jh


def _seed_vacancies(n):
    store.upsert_vacancies([
        ParsedVacancy(url=f"u{i}", title=f"Job {i}", posted_date=date(2026, 6, i + 1))
        for i in range(n)
    ])


def test_unscored_and_save_and_list(tmp_path):
    store.configure(str(tmp_path / "c.db"))
    store.init_db()
    _seed_vacancies(3)
    rows, _ = store.list_vacancies()
    ids = [r.id for r in rows]

    assert set(jh.unscored_vacancy_ids(profile_id=1, limit=10)) == set(ids)

    jh.save_candidacy(Candidacy(profile_id=1, vacancy_id=ids[0], score=90,
                                verdict="apply", status="shortlisted"))
    assert len(jh.unscored_vacancy_ids(profile_id=1, limit=10)) == 2

    items, total = jh.list_candidacies(profile_id=1)
    assert total == 1 and items[0].score == 90
    # ids[0] comes from list_vacancies() sorted posted_date DESC → first row = "Job 2"
    assert items[0].title == rows[0].title


def test_list_filters(tmp_path):
    store.configure(str(tmp_path / "c2.db"))
    store.init_db()
    _seed_vacancies(2)
    rows, _ = store.list_vacancies()
    jh.save_candidacy(Candidacy(profile_id=1, vacancy_id=rows[0].id, score=90,
                                verdict="apply", status="shortlisted"))
    jh.save_candidacy(Candidacy(profile_id=1, vacancy_id=rows[1].id, score=20,
                                verdict="skip", status="skipped"))
    assert jh.list_candidacies(profile_id=1, status="shortlisted")[1] == 1
    assert jh.list_candidacies(profile_id=1, min_score=50)[1] == 1
