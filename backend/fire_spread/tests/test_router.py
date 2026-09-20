import asyncio
import json
from pathlib import Path

import httpx
import pytest
import yaml
from fastapi import FastAPI
from jsonschema import Draft202012Validator

from fire_spread import router as r
from fire_spread.models import (
    ArrivalGrid, ElmfireTimeout, OutsideCoverage, WeatherProviderError, WeatherSummary,
)
from fire_spread.settings import Settings

OPENAPI = Path(__file__).resolve().parents[1] / "openapi.yaml"


def _grid(**kw) -> ArrivalGrid:
    base = dict(
        originLat=41.58, originLon=1.82, cellDegLat=0.00045, cellDegLon=0.0006, cellSizeM=50.0,
        durationMinutes=1440, ensembleMembers=2,
        arrivalHours=[[0, 1], [None, 2]], arrivalMinutes=[[0.0, 30.5], [None, 90.0]],
        arrivalMinutesP10=[[0.0, 25.0], [None, 80.0]], arrivalMinutesP90=[[0.0, 40.0], [None, 100.0]],
        burnProbability=[[1.0, 1.0], [0.0, 0.5]],
        weather=WeatherSummary(source="fixture", windSpeedAvgMs=5.0, windDirectionAvg=270.0),
    )
    base.update(kw)
    return ArrivalGrid(**base)


class FakePipeline:
    def __init__(self, outcome, delay=0.0):
        self.outcome, self.delay, self.calls = outcome, delay, []

    async def run(self, req, **kw):
        self.calls.append(req)
        if self.delay:
            await asyncio.sleep(self.delay)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


@pytest.fixture
def app(monkeypatch):
    def make(outcome, delay=0.0, **settings):
        fake = FakePipeline(outcome, delay)
        s = Settings(acquire_timeout_s=0.05, **settings)
        monkeypatch.setattr(r, "get_pipeline", lambda: fake)
        monkeypatch.setattr(r, "get_settings", lambda: s)
        r.get_semaphore.cache_clear()
        app = FastAPI()
        app.include_router(r.router, prefix="/fire")
        return app, fake

    yield make
    r.get_semaphore.cache_clear()


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_ok_and_schema(app):
    a, fake = app(_grid())
    async with _client(a) as c:
        res = await c.get("/fire/arrival-grid", params={"lat": 41.59, "lon": 1.83, "ensembleMembers": 2})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["arrivalHours"][1][0] is None and body["arrivalMinutes"][0][1] == 30.5
    assert "debug" not in body
    req = fake.calls[0]
    assert (req.ignition.lat, req.ignition.lon, req.ensemble_members, req.duration_hours) == (41.59, 1.83, 2, 24)

    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    schema = {**spec["components"]["schemas"]["ArrivalGrid"], "components": spec["components"]}
    Draft202012Validator(schema).validate(body)


async def test_query_validation(app):
    a, _ = app(_grid())
    async with _client(a) as c:
        assert (await c.get("/fire/arrival-grid", params={"lat": 91, "lon": 0})).status_code == 422
        assert (await c.get("/fire/arrival-grid", params={"lat": 41, "lon": 1, "ensembleMembers": 65})).status_code == 422
        assert (await c.get("/fire/arrival-grid", params={"lat": 41, "lon": 1, "durationHours": 0})).status_code == 422


@pytest.mark.parametrize(
    "exc,status",
    [
        (OutsideCoverage("ignition on a non-burnable cell"), 422),
        (WeatherProviderError("Open-Meteo returned 503"), 502),
        (ElmfireTimeout("ELMFIRE exceeded 900 s"), 504),
    ],
)
async def test_error_mapping(app, exc, status):
    a, _ = app(exc)
    async with _client(a) as c:
        res = await c.get("/fire/arrival-grid", params={"lat": 41.59, "lon": 1.83})
    assert res.status_code == status
    assert str(exc) in res.json()["detail"]


async def test_busy_returns_503(app):
    a, _ = app(_grid(), delay=0.5, max_concurrent_runs=1)
    async with _client(a) as c:
        t1 = asyncio.create_task(c.get("/fire/arrival-grid", params={"lat": 41.59, "lon": 1.83}))
        await asyncio.sleep(0.1)
        r2 = await c.get("/fire/arrival-grid", params={"lat": 41.59, "lon": 1.83})
        r1 = await t1
    assert r1.status_code == 200
    assert r2.status_code == 503


async def test_health_and_data_info(app, tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"grid": {"epsg": 25831}}))
    a, _ = app(_grid(), data_dir=tmp_path)
    async with _client(a) as c:
        h = (await c.get("/fire/health")).json()
        assert h["status"] == "ok" and h["dataPresent"] is False
        assert (await c.get("/fire/data-info")).json() == {"grid": {"epsg": 25831}}
