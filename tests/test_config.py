from liza.config import Settings


def test_keywords_list_splits_csv_and_trims():
    s = Settings(djinni_keywords="Python, JavaScript ,, QA")
    assert s.keywords_list == ["Python", "JavaScript", "QA"]


def test_keywords_list_empty_when_blank():
    s = Settings(djinni_keywords="")
    assert s.keywords_list == []


def test_matching_settings_defaults():
    s = Settings()
    assert s.llm_model_score == "openai/gpt-4o-mini"
    assert s.openrouter_base_url.startswith("https://")
    assert s.match_default_limit > 0


def test_normalized_env_tolerates_malformed_name():
    from liza.config import _normalized_env
    # trailing newline in the env var NAME (hosting-dashboard paste gotcha)
    assert _normalized_env("OPENROUTER_API_KEY", {"OPENROUTER_API_KEY\n": "sk-test"}) == "sk-test"
    # surrounding whitespace in value
    assert _normalized_env("OPENROUTER_API_KEY", {"OPENROUTER_API_KEY": " sk-x "}) == "sk-x"
    # absent
    assert _normalized_env("OPENROUTER_API_KEY", {"OTHER": "y"}) == ""
