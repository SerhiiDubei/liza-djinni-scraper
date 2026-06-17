from liza.models import ParsedVacancy
from liza.storage import repo


def _setup(tmp_path):
    repo.configure(str(tmp_path / "test.db"))
    repo.init_db()


def test_upsert_inserts_then_updates_same_url(tmp_path):
    _setup(tmp_path)
    p = ParsedVacancy(url="https://djinni.co/jobs/1/", title="Python Dev",
                      category="Python", work_format="remote", salary_max=5000)
    assert repo.upsert_vacancies([p]) == (1, 0)

    rows, _ = repo.list_vacancies()
    first_seen = rows[0].first_seen

    assert repo.upsert_vacancies([p]) == (0, 1)   # same url -> update
    rows, total = repo.list_vacancies()
    assert total == 1
    assert rows[0].first_seen == first_seen        # first_seen preserved
    assert rows[0].last_seen >= first_seen


def test_list_vacancies_filters(tmp_path):
    _setup(tmp_path)
    repo.upsert_vacancies([
        ParsedVacancy(url="u1", title="Senior Python Dev", category="Python",
                      work_format="remote", salary_max=6000),
        ParsedVacancy(url="u2", title="QA Manual", category="QA", salary_max=2000),
    ])
    assert repo.list_vacancies(category="Python")[1] == 1
    assert repo.list_vacancies(remote=True)[1] == 1
    assert repo.list_vacancies(q="python")[1] == 1        # case-insensitive contains
    assert repo.list_vacancies(salary_min=5000)[1] == 1

    rows, _ = repo.list_vacancies()
    assert repo.get_vacancy(rows[0].id) is not None
    assert repo.get_vacancy(999999) is None
