"""Briefing orchestration: LLM -> validate -> retry once -> template fallback.

Every attempt is logged to ``logs/briefings.jsonl``. When no
``NEBIUS_API_KEY`` is configured the deterministic template path is used
directly — always valid by construction.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

from app.briefing.llm import LLMError, call_llm
from app.briefing.templates import template_briefing
from app.briefing.validator import validate_briefing
from app.decision_config import DATA_ROOT, Config

log = logging.getLogger(__name__)
LOG_FILE = DATA_ROOT / "logs" / "briefings.jsonl"


def _facts_hash(facts: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(facts, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]


def _log_attempt(
    facts_hash: str, outcome: str, issues: list[str], latency_ms: int, model: str | None
) -> None:
    """Append one JSONL record per briefing attempt."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "ts": datetime.now(UTC).isoformat(),
                        "facts_hash": facts_hash,
                        "outcome": outcome,
                        "model": model,
                        "issues": issues,
                        "latency_ms": latency_ms,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except OSError:
        log.warning("could not write briefing log", exc_info=True)


def generate_briefing(facts: dict[str, Any], config: Config | None = None) -> dict[str, Any]:
    """Produce a verified trilingual briefing.

    Order: LLM attempt → validate → one retry with validator issues →
    deterministic template fallback. ``issues`` records why the LLM path
    was abandoned when falling back.
    """
    start = time.perf_counter()
    facts_hash = _facts_hash(facts)
    model = config.nebius_model if config else None
    issues: list[str] = []
    outcome = "template"

    if config and config.nebius_api_key:
        try:
            candidate = call_llm(facts, config)
            issues = validate_briefing(candidate, facts)
            if issues:
                outcome = "llm_retry"
                candidate = call_llm(facts, config, issues=issues)
                issues = validate_briefing(candidate, facts)
            if not issues:
                latency_ms = int((time.perf_counter() - start) * 1000)
                _log_attempt(facts_hash, "llm", [], latency_ms, model)
                return {
                    "briefing": candidate,
                    "source": "llm",
                    "verified": True,
                    "issues": [],
                    "model": model,
                    "latency_ms": latency_ms,
                }
        except LLMError as exc:
            issues = [f"llm_error: {exc}"]
        outcome = "llm_fallback"

    texts = template_briefing(facts)
    latency_ms = int((time.perf_counter() - start) * 1000)
    _log_attempt(facts_hash, outcome, issues, latency_ms, model)
    return {
        "briefing": texts,
        "source": "template",
        "verified": True,
        "issues": issues,
        "model": model if outcome == "llm_fallback" else None,
        "latency_ms": latency_ms,
    }
