"""Settings parsing.

The case that matters here is a variable that is *set but blank*. Compose
writes `OVERPASS_URLS: ${OVERPASS_URLS:-}`, which expands to an empty string
when the host has not set it, and a list-typed setting is JSON-decoded inside
the settings source — so a blank value used to raise SettingsError from
`Settings()`, at import time, before uvicorn could serve a single route. The
whole API answered nothing because one optional mirror list was empty.
"""

import pytest
from pydantic_settings import SettingsError

from app.config import Settings

DB_URL = "postgresql://u:p@localhost:5432/d"


def _settings(monkeypatch, **env: str) -> Settings:
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    # env_file would otherwise layer a developer's real backend/.env on top.
    return Settings(_env_file=None)


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_overpass_urls_is_empty_not_an_error(monkeypatch, blank):
    assert _settings(monkeypatch, OVERPASS_URLS=blank).overpass_urls == []


def test_unset_overpass_urls_keeps_the_default(monkeypatch):
    monkeypatch.delenv("OVERPASS_URLS", raising=False)
    assert _settings(monkeypatch).overpass_urls == []


def test_json_array_still_parses(monkeypatch):
    urls = _settings(
        monkeypatch, OVERPASS_URLS='["https://a.example/api", "https://b.example/api"]'
    ).overpass_urls
    assert urls == ["https://a.example/api", "https://b.example/api"]


def test_bare_url_is_read_as_one_mirror(monkeypatch):
    urls = _settings(monkeypatch, OVERPASS_URLS="https://a.example/api").overpass_urls
    assert urls == ["https://a.example/api"]


def test_comma_separated_urls_are_read_in_order(monkeypatch):
    urls = _settings(
        monkeypatch, OVERPASS_URLS="https://a.example/api, https://b.example/api"
    ).overpass_urls
    assert urls == ["https://a.example/api", "https://b.example/api"]


def test_blank_cors_origins_is_still_rejected(monkeypatch):
    # Left strict on purpose: this field defaults to ["*"], so reading blank as
    # [] would silently mean "no browser origin may call this API" — a failure
    # that shows up as an unexplained CORS error in someone's console rather
    # than as a message at startup.
    with pytest.raises(SettingsError):
        _settings(monkeypatch, CORS_ORIGINS="")
