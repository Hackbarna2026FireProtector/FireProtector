"""Thin client for Deepfire's fire-spread simulation API.

See docs/deepfire-api.md for the empirically verified behaviour this relies on.
"""

import asyncio
import time

import httpx
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

DURATION_HOURS = 24
MODEL = "elmfire"
# Above 1, the API reports how much of the ensemble burned each perimeter as
# `burn_probability`. That field is the only measure of forecast confidence it
# exposes, and the decision layer's scoring uses it; a single-member run omits
# it entirely. Deepfire accepts 1-50.
ENSEMBLE_MEMBERS = 10
TERMINAL_STATUSES = {"COMPLETED", "NO_SPREAD", "FAILED"}
POLL_INTERVAL_S = 5.0  # docs recommend ~10s; sims usually finish in <1 min
MAX_WAIT_S = 1200.0  # Deepfire itself times out a sim to FAILED after 60 min


class DeepfireError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


DEEPFIRE_BASE_URL = "https://api.deepfire.co"


class DeepfireClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        http: httpx.AsyncClient | None = None,
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http or httpx.AsyncClient(base_url=DEEPFIRE_BASE_URL, timeout=60)
        self._token: str | None = None
        self._token_exp: float = 0.0
        self._token_lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._http.aclose()

    # -- auth ---------------------------------------------------------------

    async def _get_token(self, force: bool = False) -> str:
        async with self._token_lock:
            if not force and self._token and time.time() < self._token_exp - 30:
                return self._token
            r = await self._http.post(
                "/v1/token",
                json={"client_id": self._client_id, "client_secret": self._client_secret},
            )
            if r.status_code != 200:
                raise DeepfireError(f"token request failed: {r.status_code} {r.text}")
            body = r.json()
            self._token = body["access_token"]
            self._token_exp = time.time() + float(body.get("expires_in", 3600))
            return self._token

    async def _request(self, method: str, url: str, **kw) -> httpx.Response:
        headers = dict(kw.pop("headers", None) or {})
        token = await self._get_token()
        headers["Authorization"] = f"Bearer {token}"
        r = await self._http.request(method, url, headers=headers, **kw)
        if r.status_code == 401:
            token = await self._get_token(force=True)
            headers["Authorization"] = f"Bearer {token}"
            r = await self._http.request(method, url, headers=headers, **kw)
        return r

    # -- fire spread --------------------------------------------------------

    async def run_simulation(self, lat: float, lon: float) -> list[tuple[int, BaseGeometry]]:
        """Queue a point-ignition simulation, block until done, return (hour, perimeter) sorted by hour.

        Only the perimeters every ensemble member agrees on. The lower-
        probability fringes are dropped here because callers of this method
        assume perimeters nest -- hour h contains hour h-1 -- and a fringe
        polygon does not.
        """
        perimeters = await self.run_simulation_detailed(lat, lon)
        certain = max((p for _, p, _ in perimeters), default=1.0)
        return [(hour, geom) for hour, prob, geom in perimeters if prob >= certain]

    async def run_simulation_detailed(
        self, lat: float, lon: float
    ) -> list[tuple[int, float, BaseGeometry]]:
        """As above, but keeping each perimeter's ensemble agreement.

        Returns ``(hour, burn_probability, perimeter)``. With ENSEMBLE_MEMBERS
        above 1 the API returns, per hour, the core all members burned at
        probability 1.0 and -- at the final hour -- additional envelopes at
        lower probabilities. That is the only real measure of forecast
        confidence available, so the decision layer scores against it; see
        docs/deepfire-api.md.
        """
        r = await self._request(
            "POST",
            "/v1/fire-spread/simulations",
            json={
                "latitude": lat,
                "longitude": lon,
                "durationHours": DURATION_HOURS,
                "model": MODEL,
                "ensembleMembers": ENSEMBLE_MEMBERS,
            },
        )
        if r.status_code == 429 or r.status_code == 503:
            raise DeepfireError(f"Deepfire rate/concurrency limit: {r.text}", 503)
        if r.status_code >= 400:
            raise DeepfireError(f"create simulation failed: {r.status_code} {r.text}", 502)
        sim_id = r.json()["id"]

        deadline = time.monotonic() + MAX_WAIT_S
        while True:
            r = await self._request("GET", f"/v1/fire-spread/simulations/{sim_id}")
            if r.status_code >= 400:
                raise DeepfireError(f"poll failed: {r.status_code} {r.text}", 502)
            body = r.json()
            status = body.get("status")
            if status in TERMINAL_STATUSES:
                break
            if time.monotonic() > deadline:
                raise DeepfireError(f"simulation {sim_id} still {status} after {MAX_WAIT_S}s", 504)
            await asyncio.sleep(POLL_INTERVAL_S)

        if status == "FAILED":
            msg = body.get("errorMessage") or "simulation failed"
            code = 422 if "outside the supported simulation areas" in msg else 502
            raise DeepfireError(msg, code)

        hourly: list[tuple[int, float, BaseGeometry]] = []
        for feat in (body.get("result") or {}).get("features", []):
            props = feat.get("properties") or {}
            hour = props.get("hour")
            if hour is None and props.get("elapsed_seconds") is not None:
                hour = round(props["elapsed_seconds"] / 3600)
            if hour is None or feat.get("geometry") is None:
                continue
            # Absent on a single-member run, where every perimeter is certain.
            prob = props.get("burn_probability")
            prob = 1.0 if prob is None else float(prob)
            hourly.append((int(hour), prob, shape(feat["geometry"])))
        # Descending probability within an hour, so the certain core comes
        # first and `max` in run_simulation has a stable thing to compare.
        hourly.sort(key=lambda t: (t[0], -t[1]))
        return hourly
