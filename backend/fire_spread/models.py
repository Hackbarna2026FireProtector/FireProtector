"""Request / response models shared by the router, pipeline and CLI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class Ignition:
    """Fire state input. v1: a point. An active perimeter can be added later as an
    alternative that renders a ``phi`` raster instead of ``X_IGN/Y_IGN``."""

    lat: float
    lon: float


@dataclass
class SimulationRequest:
    ignition: Ignition
    duration_hours: int = 24
    ensemble_members: int = 16
    start_time: datetime | None = None
    seed: int | None = None
    spotting: bool | None = None  # None -> settings.spotting_default
    debug: bool = False

    def to_json(self) -> dict:
        return {
            "lat": self.ignition.lat,
            "lon": self.ignition.lon,
            "durationHours": self.duration_hours,
            "ensembleMembers": self.ensemble_members,
            "startTime": self.start_time.isoformat() if self.start_time else None,
            "seed": self.seed,
            "spotting": self.spotting,
        }


class WeatherSummary(BaseModel):
    source: str
    windSpeedAvgMs: float
    windDirectionAvg: float
    windSpeedSigmaMs: float | None = None
    windDirectionSigmaDeg: float | None = None
    fuelMoisture1hAvgPct: float | None = None
    fuelMoisture100hAvgPct: float | None = None
    liveHerbaceousPct: float | None = None
    liveWoodyPct: float | None = None
    foliarMoisturePct: float | None = None
    weatherMembers: int | None = None  # NWP ensemble members driving the cases (1 = perturbed deterministic)


class ZoneInfo(BaseModel):
    name: str | None = None
    dominantFireType: str | None = None
    designFires: dict[str, float] = Field(default_factory=dict)
    properties: dict = Field(default_factory=dict)


class DebugInfo(BaseModel):
    runId: str
    runDir: str
    timings: dict[str, float]
    elmfireStdoutTail: str


class ArrivalGrid(BaseModel):
    originLat: float
    originLon: float
    cellDegLat: float
    cellDegLon: float
    cellSizeM: float
    durationMinutes: int
    ensembleMembers: int
    arrivalHours: list[list[int | None]]
    arrivalMinutes: list[list[float | None]]
    arrivalMinutesP10: list[list[float | None]]
    arrivalMinutesP90: list[list[float | None]]
    burnProbability: list[list[float | None]]
    weather: WeatherSummary
    physics: dict = Field(default_factory=dict)  # switches that shaped this run (spotting, barriers, diurnal...)
    zone: ZoneInfo = Field(default_factory=ZoneInfo)
    debug: DebugInfo | None = None


# --- errors -------------------------------------------------------------------


class PipelineError(Exception):
    status_code = 500


class OutsideCoverage(PipelineError):
    """Ignition outside the static data, or on a non-burnable cell."""

    status_code = 422


class WeatherProviderError(PipelineError):
    status_code = 502


class ElmfireTimeout(PipelineError):
    status_code = 504


class ElmfireFailed(PipelineError):
    status_code = 500
