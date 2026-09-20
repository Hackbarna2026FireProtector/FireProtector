"""Runtime configuration (environment variables / .env)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Path("data/fire_spread/catalonia")
    runs_dir: Path = Path("data/fire_spread/runs")
    elmfire_nproc: int = 4
    elmfire_timeout_s: float = 15 * 60
    open_meteo_base_url: str = "https://api.open-meteo.com"
    open_meteo_ensemble_base_url: str = "https://ensemble-api.open-meteo.com"
    # NWP ensemble driving the cases. icon_eu_eps: 40 members, 13 km, hourly, but no humidity
    # (members reuse the deterministic RH); ecmwf_ifs025: 50 members, 25 km, all variables.
    open_meteo_ensemble_model: str = "icon_eu_eps"
    weather_fixture: Path | None = None  # JSON file → FixtureProvider instead of Open-Meteo
    keep_runs: Literal["all", "failed", "none"] = "failed"
    max_concurrent_runs: int = 1
    acquire_timeout_s: float = 3.0  # how long a request waits for a free slot before 503

    # --- domain / resolution ---
    domain_size_m: float = 40_000.0
    cell_size_m: float | None = None  # None -> native resolution of the static tier
    ignition_frac: float = 1 / 3  # ignition position from the upwind edge (0.5 = centred)

    # --- weather ---
    weather_grid_n: int = 4  # coarse weather raster: n x n points over the domain (1 = uniform)
    weather_bilinear: bool = True  # ELMFIRE-side bilinear interpolation of the weather grid
    weather_ensemble: bool = True  # run cases on real NWP ensemble members when available
    weather_history_hours: int = 48  # spin-up for the time-lagged 10-h / 100-h fuel moistures
    lh_moisture_pct: float | None = None  # None -> monthly climatology (weather.live_fuel_moisture)
    lw_moisture_pct: float | None = None
    foliar_moisture_pct: float | None = None  # None -> monthly climatology (weather.foliar_moisture)

    # --- physics ---
    hindcast: bool = False  # ignore burn scars of the ignition year (the simulated fire is in burnyear.tif)
    adj_factor: float = 1.0  # global spread-rate multiplier (ADJ raster); first calibration knob
    use_barriers: bool = True  # if data_dir/barrier.tif exists (roads/rivers width raster)
    diurnal_adjustment: bool = True  # Rothermel night-time over-prediction damping
    overnight_adjustment_factor: float = 0.4  # ELMFIRE default 0.1 is aggressive for shrub fuels
    max_low: float = 8.0  # cap on fire-ellipse length/width (lower = fewer cigar fires)
    crown_ratio: float = 1.0
    spotting_default: bool = False  # ember transport (expensive); requests can override
    fuel_model_set: Literal["scott_burgan", "mediterranean"] = "scott_burgan"  # see fire_spread/fuels.py

    @property
    def barrier_path(self) -> Path:
        return self.data_dir / "barrier.tif"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
