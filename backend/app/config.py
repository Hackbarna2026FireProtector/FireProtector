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

    # Where the building data lives. Kept configurable so the API does not have to
    # change when the asset dataset is loaded under a different name.
    building_specs_table: str = "building_specs"
    latitude_column: str = "latitude"
    longitude_column: str = "longitude"

    # Result caps for /building_specs.
    default_limit: int = 500
    max_limit: int = 10_000

    # Cap on rows accepted by a single /add_building request.
    max_insert_rows: int = 1_000

    # Connection pool sizing (Neon's pooled endpoint handles the rest).
    pool_min_size: int = 1
    pool_max_size: int = 10

    cors_origins: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
