"""Grounding validator for LLM briefings (spec §8.5).

Five checks per language:
1. **shape**    — ``{"en": str, "es": str, "ca": str}`` non-empty.
2. **length**   — ≤ 150 words per language (prompt targets 120, §8.1).
3. **numeric**  — every number in the text must appear in the facts object
                  (raw or rounded forms; local HH:MM times are allowed).
4. **entities** — capitalised name phrases must appear verbatim in facts.
5. **scope**    — no claims outside the data (casualties, evacuation orders,
                  road closures, weather causes).
6. **language** — stopword scoring must match the expected language.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.briefing.templates import LANGUAGES

MAX_WORDS = 150

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
_NAME_RE = re.compile(
    r"\b([A-ZÀ-Þ][\w'’.-]*(?:\s+(?:de|del|la|els?|das?|i|l'|d')\s+|\s+)[A-ZÀ-Þ][\w'’.-]*)+"
)

# Claims the system cannot support — keep briefings inside the facts.
_FORBIDDEN = re.compile(
    r"(evacu|\bcasualt|fatal|injur|muert|víctim|victima|ferit|cerrad|tallat|"
    r"road\s*clos|school\s*clos|arson|piroman|lightning|llampec)",
    re.IGNORECASE,
)

_STOPWORDS = {
    "en": {"the", "of", "and", "in", "is", "to", "are", "within", "as", "with", "at"},
    "es": {"el", "la", "de", "y", "en", "los", "las", "del", "con", "una", "por"},
    "ca": {"el", "la", "de", "i", "en", "els", "les", "del", "amb", "una", "per"},
}


def _numbers_in(obj: Any, out: set[str]) -> None:
    """Collect every number in facts as acceptable surface forms."""
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float)):
        for fmt in (
            f"{obj:g}",
            f"{round(obj)}",
            f"{obj:.0f}",
            f"{obj:.1f}",
            f"{obj:.2f}",
            f"{round(obj * 100)}",
            f"{obj * 100:.0f}",
        ):
            out.add(fmt)
        return
    if isinstance(obj, dict):
        for v in obj.values():
            _numbers_in(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _numbers_in(v, out)
    elif isinstance(obj, str):
        out.update(_NUMBER_RE.findall(obj))  # times like 14:00 inside ISO strings


def _facts_strings(facts: dict[str, Any]) -> str:
    """All string/number content of facts as one searchable blob."""
    return json.dumps(facts, ensure_ascii=False)


def _detect_language(text: str) -> str:
    """Majority stopword vote — enough to catch wrong-language outputs."""
    words = set(re.findall(r"[a-zàèéíòóúçñ']+", text.lower()))
    scores = {lang: len(words & sw) for lang, sw in _STOPWORDS.items()}
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "en"


def _capitalised_phrases(text: str) -> list[str]:
    """Multi-word capitalised phrases, minus sentence starts."""
    phrases = []
    for m in re.finditer(r"(?<=[.!?\s])([A-ZÀ-Þ][\wÀ-ÿ'’.-]*(?:\s+[A-ZÀ-Þ][\wÀ-ÿ'’.-]*)+)", text):
        phrases.append(m.group(1))
    return phrases


def validate_briefing(payload: Any, facts: dict[str, Any]) -> list[str]:
    """Return a list of issues; empty means the briefing is grounded."""
    issues: list[str] = []
    if not isinstance(payload, dict):
        return ["shape: response is not a JSON object"]
    texts: dict[str, str] = {}
    for lang in LANGUAGES:
        text = payload.get(lang)
        if not isinstance(text, str) or not text.strip():
            issues.append(f"shape: missing or empty '{lang}'")
        else:
            texts[lang] = text
    if issues:
        return issues

    allowed_numbers: set[str] = set()
    _numbers_in(facts, allowed_numbers)
    facts_blob = _facts_strings(facts)

    for lang in LANGUAGES:
        issues.extend(_check_language(texts[lang], lang, allowed_numbers, facts_blob))
    return issues


def _check_language(text: str, lang: str, allowed_numbers: set[str], facts_blob: str) -> list[str]:
    """All per-language grounding checks for one briefing text."""
    issues: list[str] = []
    words = text.split()
    if len(words) > MAX_WORDS:
        issues.append(f"length[{lang}]: {len(words)} words > {MAX_WORDS}")

    for raw in _NUMBER_RE.findall(text):
        norm = raw.replace(",", ".")
        if norm not in allowed_numbers and raw not in allowed_numbers:
            issues.append(f"numeric[{lang}]: {raw} not in facts")

    for phrase in _capitalised_phrases(text):
        if phrase not in facts_blob:
            issues.append(f"entity[{lang}]: {phrase!r} not in facts")

    m = _FORBIDDEN.search(text)
    if m:
        issues.append(f"scope[{lang}]: unsupported claim {m.group(0)!r}")

    detected = _detect_language(text)
    if detected != lang:
        issues.append(f"language[{lang}]: detected {detected}")
    return issues
