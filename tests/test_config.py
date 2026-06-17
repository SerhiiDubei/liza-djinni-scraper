from liza.config import Settings


def test_keywords_list_splits_csv_and_trims():
    s = Settings(djinni_keywords="Python, JavaScript ,, QA")
    assert s.keywords_list == ["Python", "JavaScript", "QA"]


def test_keywords_list_empty_when_blank():
    s = Settings(djinni_keywords="")
    assert s.keywords_list == []
