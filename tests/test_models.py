from liza.models import ParsedVacancy, Vacancy


def test_parsed_vacancy_requires_only_url_and_title():
    p = ParsedVacancy(url="https://djinni.co/jobs/1/", title="Dev")
    assert p.url.endswith("/1/")
    assert p.company is None
    assert p.salary_min is None


def test_vacancy_is_a_table_model():
    assert Vacancy.__tablename__ == "vacancy"
