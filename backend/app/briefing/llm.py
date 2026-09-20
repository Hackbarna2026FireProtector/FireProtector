"""Nebius Token Factory client (OpenAI-compatible chat completions).

The prompt carries ONLY the computed facts object — never free-form data.
Responses are cached on disk keyed by sha256(facts, model, prompt version).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import requests

from app.decision_config import DATA_ROOT, Config

PROMPT_VERSION = "v1"
LLM_TIMEOUT_S = 20.0
CACHE_DIR = DATA_ROOT / "cache" / "briefings"

SYSTEM_PROMPT = """You are a wildfire incident analyst writing a situation briefing for emergency managers.

RULES — violations make the briefing invalid:
- Use ONLY the numbers and asset names in the FACTS JSON below. Never invent figures, names, casualties, evacuations, road closures, or causes.
- Times are Europe/Madrid local.
- Tone: factual, operational, no speculation, no advice beyond the data.

Write a short briefing (max 120 words per language) covering: fire name and reference time, how many of the tracked assets are threatened within the horizon, the highest-risk assets (name + ETA + confidence), mean confidence, and ranking robustness.

Respond with ONLY a JSON object, no markdown:
{"en": "<english briefing>", "es": "<spanish briefing>", "ca": "<catalan briefing>"}"""


class LLMError(RuntimeError):
    """The briefing model call failed or returned unusable content."""


def cache_key(facts: dict[str, Any], model: str, attempt: int = 0) -> str:
    """Deterministic cache key over facts + model + prompt version + attempt."""
    blob = json.dumps(
        {"facts": facts, "model": model, "v": PROMPT_VERSION, "attempt": attempt},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


def _read_cache(key: str) -> dict[str, str] | None:
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(cached, dict):
                return {k: v for k, v in cached.items() if isinstance(v, str)}
        except (OSError, json.JSONDecodeError):
            return None
    return None


def _write_cache(key: str, payload: dict[str, str]) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (CACHE_DIR / f"{key}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass


def build_messages(facts: dict[str, Any], issues: list[str] | None = None) -> list[dict[str, str]]:
    """Prompt messages; on retry, the validator issues are appended."""
    user = "FACTS:\n" + json.dumps(facts, ensure_ascii=False, indent=2)
    if issues:
        user += (
            "\n\nYour previous answer was rejected for these reasons — fix every one:\n"
            + "\n".join(f"- {i}" for i in issues)
        )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _extract_json(content: str) -> dict[str, Any]:
    """Parse the model output, tolerating stray prose/markdown fences."""
    text = content.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise LLMError("model did not return a JSON object")
    return json.loads(text[start : end + 1])


def call_llm(
    facts: dict[str, Any],
    config: Config,
    issues: list[str] | None = None,
    session: requests.Session | None = None,
    use_cache: bool = True,
) -> dict[str, str]:
    """Call Nebius chat completions; return the raw ``{en, es, ca}`` dict.

    Raises ``LLMError`` on transport, HTTP, or parse failures.
    """
    attempt = 1 if issues else 0
    key = cache_key(facts, config.nebius_model, attempt)
    if use_cache:
        cached = _read_cache(key)
        if cached is not None:
            return cached

    url = config.nebius_base_url.rstrip("/") + "/chat/completions"
    http = session or requests.Session()
    try:
        resp = http.post(
            url,
            headers={
                "Authorization": f"Bearer {config.nebius_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": config.nebius_model,
                "messages": build_messages(facts, issues),
                "temperature": 0.2,
                "max_tokens": 1200,
                "response_format": {"type": "json_object"},
            },
            timeout=LLM_TIMEOUT_S,
        )
    except requests.RequestException as exc:
        raise LLMError(f"nebius request failed: {exc}") from exc
    if resp.status_code != 200:
        raise LLMError(f"nebius HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        content = resp.json()["choices"][0]["message"]["content"]
        result = _extract_json(content)
    except (KeyError, IndexError, json.JSONDecodeError, TypeError) as exc:
        raise LLMError(f"unparseable model response: {exc}") from exc
    if not isinstance(result, dict):
        raise LLMError("model response is not an object")
    texts = {lang: str(result.get(lang, "")) for lang in ("en", "es", "ca")}
    if use_cache:
        _write_cache(key, texts)
    return texts
