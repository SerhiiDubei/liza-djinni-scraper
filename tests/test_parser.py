from pathlib import Path

from liza.scraper.parser import parse_jobs_page

FIXTURE = Path(__file__).parent / "fixtures" / "djinni_jobs.html"


def test_parses_jobpostings_and_skips_other_jsonld():
    vacancies, total_pages = parse_jobs_page(FIXTURE.read_text(encoding="utf-8"))
    assert len(vacancies) == 2          # BreadcrumbList ignored
    assert total_pages == 3

    a = vacancies[0]
    assert a.title == "Senior Python Developer"
    assert a.company == "ACME Corp"
    assert a.url == "https://djinni.co/jobs/123-senior-python-developer/"
    assert a.salary_min == 4000 and a.salary_max == 6000
    assert a.salary_currency == "USD"
    assert a.work_format == "remote"
    assert str(a.posted_date) == "2026-02-15"
    assert a.location == "Kyiv, UA"
    assert "Great role" in a.description    # HTML stripped
    assert a.raw_json is not None


def test_scalar_salary_sets_min_equals_max():
    vacancies, _ = parse_jobs_page(FIXTURE.read_text(encoding="utf-8"))
    b = vacancies[1]
    assert b.salary_min == 1500 and b.salary_max == 1500


def test_empty_page_returns_no_vacancies_and_one_page():
    vacancies, total_pages = parse_jobs_page("<html><body>No jobs</body></html>")
    assert vacancies == []
    assert total_pages == 1


def test_jobposting_with_type_as_list_is_parsed():
    html = (
        '<html><body><script type="application/ld+json">'
        '{"@type": ["JobPosting", "Thing"], "title": "Listy Dev",'
        ' "url": "https://djinni.co/jobs/789/"}'
        '</script></body></html>'
    )
    from liza.scraper.parser import parse_jobs_page
    vacancies, _ = parse_jobs_page(html)
    assert len(vacancies) == 1
    assert vacancies[0].title == "Listy Dev"
