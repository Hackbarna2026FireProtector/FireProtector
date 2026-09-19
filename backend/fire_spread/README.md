# Fire arrival grid API

Given an ignition point, run a Deepfire fire-spread simulation and return a grid where each cell holds the hour the fire first reaches it.

Mounted into the FireProtector API at `/fire` (`app/main.py`), so the route is `GET /fire/arrival-grid`. The package talks to Deepfire over HTTP and never touches Postgres, which is why it sits beside `app/` rather than in `app/routers/`.

## Setup

The stack already carries it: `DEEPFIRE_CLIENT_ID` / `DEEPFIRE_CLIENT_SECRET` go in `backend/.env` (see `.env.example`), `docker-compose.yml` passes them into the container, and `fire_spread/` is both copied into the image and mounted for `--reload`.

```sh
cd backend && docker compose up -d --build api
```

Without the credentials the route answers 500 and the rest of the API is unaffected. Running on the host works the same way — `load_dotenv()` reads `backend/.env`, and a real environment variable wins over it:

```sh
cd backend && .venv/bin/uvicorn app.main:app --reload
```

To mount it in a different app:

```python
from fastapi import FastAPI
from fire_spread import router

app = FastAPI()
app.include_router(router, prefix="/fire")
```

## Request

```sh
curl 'localhost:5102/fire/arrival-grid?lat=34.5&lon=-119.8'
```

Blocking: waits for the Deepfire sim (usually < 1 min, up to 20 min before a 504). Ignition must be in continental US, Europe or Hawaii (422 otherwise). 503 = Deepfire concurrency/rate limit hit. Duration is fixed at 24 h, model `elmfire`, cell size 100 m.

## Response

```json
{
  "originLat": 34.48,
  "originLon": -119.83,
  "cellDegLat": 0.000898,
  "cellDegLon": 0.00109,
  "arrivalHours": [[null, null, 6, 5, ...], ...]
}
```

`arrivalHours[row][col]`: row 0 is the southernmost row, col 0 the westernmost. Cell `(row, col)` covers `[originLon + col*cellDegLon, +cellDegLon) × [originLat + row*cellDegLat, +cellDegLat)`; the origin is the south-west corner of cell `[0][0]`. `null` = not reached within 24 h. The ignition cell holds `0`; other cells hold the first hour (1..24) whose perimeter contains the cell centre.

## Errors

Errors come back in the API-wide envelope, not FastAPI's `{"detail": ...}`, because `install_handlers()` in `app/errors.py` is installed application-wide:

```json
{ "error": { "code": "upstream_error", "message": "create simulation failed: ..." } }
```

`openapi.yaml` describes the route as it behaves mounted here. Note that a bad `lat`/`lon` comes back as **400**, not 422 — the app remaps FastAPI's validation status for the asset-register contract, and that remap is global.

## Notes

`docs/deepfire-api.md` has the empirically verified Deepfire behaviour this relies on — including the 24 h/model/geography limits and the fact that hourly perimeters are nested, which is what makes the newest→oldest rasterising pass in `grid.py` correct.
