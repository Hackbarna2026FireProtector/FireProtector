"""Application settings, loaded from the environment (and a local .env file)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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


@lru_cache
def get_settings() -> Settings:
    return Settings()
