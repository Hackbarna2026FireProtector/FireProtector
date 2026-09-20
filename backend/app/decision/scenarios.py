"""Ignition scenarios, read from the seed file.

A scenario is a hypothetical ignition at a chosen coordinate — nobody detected
it, so it carries no detection time and no containment status. That is the
whole concept; see CONTEXT.md.

The engine's ported ``Fire`` dataclass is what the exposure and briefing code
expects, and it has fields a scenario does not: ``detected_at`` and ``status``.
Rather than invent values for them, ``as_engine_fire`` fills them from the
scenario's declared time and a fixed ``"scenario"`` marker, and nothing outside
the engine ever sees them. The wire shape under /api is scenario-shaped.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from app.engine.contracts import Fire

_SEED_FILE = Path(__file__).resolve().parent.parent / "data" / "scenarios.json"


class ScenarioNotFound(KeyError):
    """No scenario with that id is defined in the seed file."""


@dataclass(frozen=True)
class Scenario:
    """A hypothetical ignition at a coordinate."""

    scenario_id: str
    name: str
    description: str
    ignition_point: BaseGeometry  # EPSG:4326
    declared_at: datetime

    @property
    def lat(self) -> float:
        return float(self.ignition_point.y)

    @property
    def lon(self) -> float:
        return float(self.ignition_point.x)

    def as_engine_fire(self) -> Fire:
        """The shape the ported engine expects, in EPSG:25831."""
        from app.engine.contracts import _reproject

        return Fire(
            fire_id=self.scenario_id,
            name=self.name,
            ignition_point=_reproject(self.ignition_point),
            detected_at=self.declared_at,
            status="scenario",
        )

    def to_dict(self) -> dict[str, Any]:
        """The /api wire shape. No detected_at, no status: neither is real."""
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "description": self.description,
            "ignition_point": self.ignition_point.__geo_interface__,
            "declared_at": self.declared_at.isoformat(),
        }


@lru_cache(maxsize=1)
def load_scenarios() -> dict[str, Scenario]:
    """Read the seed file, keyed by id and keeping the file's order."""
    payload = json.loads(_SEED_FILE.read_text(encoding="utf-8"))
    scenarios: dict[str, Scenario] = {}
    for entry in payload["scenarios"]:
        scenario = Scenario(
            scenario_id=entry["scenario_id"],
            name=entry["name"],
            description=entry.get("description", ""),
            ignition_point=shape(entry["ignition_point"]),
            declared_at=datetime.fromisoformat(entry["declared_at"]),
        )
        scenarios[scenario.scenario_id] = scenario
    return scenarios


def list_scenarios() -> list[Scenario]:
    return list(load_scenarios().values())


def get_scenario(scenario_id: str) -> Scenario:
    try:
        return load_scenarios()[scenario_id]
    except KeyError:
        raise ScenarioNotFound(scenario_id) from None
