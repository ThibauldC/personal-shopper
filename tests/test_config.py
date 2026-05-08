from pathlib import Path

from personal_shopper.config import Settings, get_settings, reset_settings


def test_default_settings():
    s = Settings()
    assert s.database_path == Path("personal_shopper.db")
    assert "delhaize.be" in s.delhaize_base_url
    assert s.delhaize_recipes_per_run == 8
    assert s.delhaize_refresh_max_urls is None


def test_recipes_url_property():
    s = Settings()
    url = s.delhaize_recipes_url
    assert url.startswith("https://")
    assert "delhaize" in url


def test_singleton_caching():
    reset_settings()
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_reset_clears_singleton():
    reset_settings()
    s1 = get_settings()
    reset_settings()
    s2 = get_settings()
    assert s1 is not s2


def test_env_override(monkeypatch):
    reset_settings()
    monkeypatch.setenv("DELHAIZE_RECIPES_PER_RUN", "12")
    monkeypatch.setenv("DELHAIZE_REFRESH_MAX_URLS", "500")
    s = Settings()
    assert s.delhaize_recipes_per_run == 12
    assert s.delhaize_refresh_max_urls == 500
    reset_settings()


def test_database_path_type():
    s = Settings()
    assert isinstance(s.database_path, Path)
