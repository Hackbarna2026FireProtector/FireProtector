"""Nebius client tests: request shape, JSON extraction, cache, errors."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.briefing import llm
from app.briefing.llm import LLMError, call_llm
from app.decision_config import Config


class _Resp:
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self.status_code = status
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeSession:
    def __init__(self, resp: _Resp) -> None:
        self.resp = resp
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> _Resp:
        self.calls.append({"url": url, **kwargs})
        return self.resp


def _config() -> Config:
    return Config(nebius_api_key="key", nebius_model="test-model")


def _ok(text: str = "Briefing text") -> _Resp:
    return _Resp(
        {"choices": [{"message": {"content": json.dumps({"en": text, "es": "x", "ca": "y"})}}]}
    )


def test_llm_request_shape(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    session = _FakeSession(_ok())
    out = call_llm({"fire": {"name": "IF X"}}, _config(), session=session)
    assert out["en"] == "Briefing text"
    call = session.calls[0]
    assert call["url"].endswith("/chat/completions")
    assert call["headers"]["Authorization"] == "Bearer key"
    assert call["json"]["model"] == "test-model"
    assert call["json"]["temperature"] == 0.2
    assert call["timeout"] == 20.0
    assert "IF X" in call["json"]["messages"][1]["content"]


def test_llm_cache_hit_skips_http(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    session = _FakeSession(_ok())
    facts = {"fire": {"name": "IF X"}}
    call_llm(facts, _config(), session=session)
    call_llm(facts, _config(), session=session)
    assert len(session.calls) == 1


def test_llm_retry_uses_separate_cache_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    session = _FakeSession(_ok())
    facts = {"fire": {"name": "IF X"}}
    call_llm(facts, _config(), session=session)
    call_llm(facts, _config(), issues=["numeric[en]: bad"], session=session)
    assert len(session.calls) == 2
    assert "bad" in session.calls[1]["json"]["messages"][1]["content"]


def test_llm_http_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    session = _FakeSession(_Resp({"error": "nope"}, status=500))
    with pytest.raises(LLMError, match="HTTP 500"):
        call_llm({}, _config(), session=session)


def test_llm_non_json_response(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    session = _FakeSession(_Resp({"choices": [{"message": {"content": "not json at all"}}]}))
    with pytest.raises(LLMError, match="JSON"):
        call_llm({}, _config(), session=session)


def test_llm_markdown_fenced_json(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    fenced = '```json\n{"en": "a", "es": "b", "ca": "c"}\n```'
    session = _FakeSession(_Resp({"choices": [{"message": {"content": fenced}}]}))
    out = call_llm({}, _config(), session=session)
    assert out == {"en": "a", "es": "b", "ca": "c"}
