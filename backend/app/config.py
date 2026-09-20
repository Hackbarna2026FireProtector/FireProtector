"""Application settings, loaded from the environment (and a local .env file)."""

import json
from functools import lru_cache
from typing import Annotated, Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Neon connection string, e.g.
    # postgresql://user:pass@ep-xxx-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require
    database_url: str

    # Where the asset data lives. Kept configurable so the API does not have to
    # change when the dataset is loaded under a different name.
    asset_specs_table: str = "protection.asset_specs"
    latitude_column: str = "latitude"
    longitude_column: str = "longitude"

    # Result caps for /building_specs.
    default_limit: int = 500
    max_limit: int = 10_000

    # Page size for /assets. The contract has no limit parameter, so a bare
    # request returns this many features plus a `next` link; ceiling and default
    # are the same number, so a caller cannot ask for a bigger page.
    assets_page_size: int = 1_000

    # Cap on rows accepted by a single /add_building request.
    max_insert_rows: int = 1_000

    # Connection pool sizing (Neon's pooled endpoint handles the rest).
    pool_min_size: int = 1
    pool_max_size: int = 10

    cors_origins: list[str] = ["*"]

    # ------------------------------------------------------------ decision --
    # Settings below belong to the decision layer under /api. Every one has a
    # working default, so the asset-register API starts unchanged without them.

    # Metres of slack around the outermost arrival contour when choosing which
    # assets to score. Small on purpose: an asset the fire never reaches scores
    # exactly zero, so a wide margin costs payload and buys nothing.
    reached_margin_m: float = 1_000.0

    # Overpass mirrors for the named critical facilities, tried in order.
    # Empty means the provider's own list; set OVERPASS_URLS as a JSON array to
    # pin a mirror when the default one is unreachable.
    overpass_urls: Annotated[list[str], NoDecode] = []

    # Nebius Token Factory, for briefings. With no key the deterministic
    # template path is used instead, which is always valid by construction.
    nebius_api_key: str = ""
    nebius_base_url: str = "https://api.tokenfactory.nebius.com/v1/"
    nebius_model: str = "meta-llama/Llama-3.3-70B-Instruct"

    # NoDecode above, and this validator, exist because a list field is
    # otherwise JSON-decoded inside the settings source, before any validation
    # runs. A variable that is set but blank — `OVERPASS_URLS=` in .env, or
    # Compose expanding `${OVERPASS_URLS:-}` for a variable unset on the host
    # — then reaches json.loads as "" and raises SettingsError, which happens
    # at import time and stops uvicorn from serving anything at all. Empty is
    # already this field's default, so read a blank value as that.
    #
    # Deliberately not applied to cors_origins: its default is ["*"], so a
    # blank value there is genuinely ambiguous, and is better rejected than
    # quietly turned into "no browser origin may call this API".
    @field_validator("overpass_urls", mode="before")
    @classmethod
    def _parse_mirror_list(cls, v: Any) -> Any:
        if not isinstance(v, str):
            return v
        v = v.strip()
        if not v:
            return []
        if v.startswith("["):
            return json.loads(v)
        # A single bare URL, or a comma-separated few, rather than the JSON
        # array the docs ask for. Unambiguous, so honour it.
        return [part.strip() for part in v.split(",") if part.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
