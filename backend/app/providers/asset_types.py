"""The editable value/vulnerability table, keyed by asset type.

One table serves two populations that reach the ranking by different routes:
the OSM critical facilities, which arrive already typed, and the INSPIRE
register rows, whose types are written into Postgres by
``db/init/03_asset_values.sql``. Keeping both in one file is what makes a
hospital and a storage tank comparable on the same 1-100 scale.

Editing this file changes the OSM side on the next request; the register side
needs the SQL re-applied, because those columns are stored, not computed.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_TABLE_PATH = Path(__file__).resolve().parent.parent / "data" / "asset_types.yaml"


@lru_cache(maxsize=1)
def asset_type_defaults() -> dict[str, Any]:
    """Load the editable value/vulnerability table per asset type."""
    return yaml.safe_load(_TABLE_PATH.read_text(encoding="utf-8"))


def value_and_vulnerability(asset_type: str) -> tuple[float, float]:
    """Look up one type, falling back to the table's documented defaults."""
    table = asset_type_defaults()
    entry = table["types"].get(asset_type, {})
    return (
        float(entry.get("value", table["defaults"]["value"])),
        float(entry.get("vulnerability", table["defaults"]["vulnerability"])),
    )
