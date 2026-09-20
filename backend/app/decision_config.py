"""Configuration for the ported decision layer.

The engine and briefing packages were written against a ``Config`` dataclass
and a repo-root path. Rather than edit them throughout, this module supplies
both, backed by the same ``Settings`` the rest of the API uses.

``DATA_ROOT`` is the one writable directory the decision layer needs: scenario
bundles, the briefing cache and the briefing log all live under it. It resolves
to ``backend/data`` on a host checkout and ``/srv/data`` inside the container,
because ``app/`` sits one level below the root in both. The container mounts it
as a volume — ``app/`` itself is read-only there, so nothing may be written
beside the code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Settings, get_settings

DATA_ROOT = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class Config:
    """The subset of settings the ported briefing code reads."""

    nebius_api_key: str = ""
    nebius_base_url: str = "https://api.tokenfactory.nebius.com/v1/"
    nebius_model: str = "meta-llama/Llama-3.3-70B-Instruct"

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> Config:
        s = settings or get_settings()
        return cls(
            nebius_api_key=s.nebius_api_key,
            nebius_base_url=s.nebius_base_url,
            nebius_model=s.nebius_model,
        )
