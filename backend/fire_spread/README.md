# Fire arrival grid API

Given an ignition point, run a Deepfire fire-spread simulation and return a grid where each cell holds the hour the fire first reaches it.

## Setup

Put `DEEPFIRE_CLIENT_ID` / `DEEPFIRE_CLIENT_SECRET` in a `.env` at the working directory you run the server from, then mount the router:

```python
from fastapi import FastAPI
from fire_spread import router

app = FastAPI()
app.include_router(router, prefix="/fire")
```

```sh
uv sync
uv run uvicorn main:app --reload   # from backend/
```

## Request

```sh
curl 'localhost:8000/fire/arrival-grid?lat=34.5&lon=-119.8'
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
