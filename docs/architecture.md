# FireProtector architecture

How a request flows through the decision layer.

```mermaid
flowchart LR
    subgraph Frontend["Frontend (React + MapLibre :5173)"]
        UI["Command-centre UI"]
    end

    subgraph Backend["FastAPI backend (:5102)"]
        API["/api decision router"]
        Bundle["Bundle cache: memory, then disk, then build"]
        Engine["Engine: exposure, scoring, sensitivity"]
        Brief["Briefing: LLM + grounding validator"]
        Contract["GET /assets contract endpoint"]
    end

    subgraph Data["Data and external services"]
        PG[("Postgres: asset register + forests")]
        Rec[("Recorded bundles JSON")]
        Deepfire["Deepfire ELMFIRE simulation"]
        OSM["OpenStreetMap Overpass"]
        LLM["Nebius LLM"]
    end

    UI -->|"HTTP /api (Vite proxy)"| API
    API -->|"get bundle"| Bundle
    Bundle -->|"read/write"| Rec
    Bundle -->|"simulate ignition (no recording)"| Deepfire
    Bundle -->|"reached-area asset query"| PG
    Bundle -->|"named facilities"| OSM
    API -->|"score / sensitivity"| Engine
    API -->|"briefing facts"| Brief
    Brief -->|"chat completions"| LLM
    Contract -->|"bbox query"| PG
```

The UI only talks to `/api`. Each route asks for the scenario's *bundle*: the
fire-spread forecast, the reached assets and the exposure join. A bundle comes
from memory, then from a recorded JSON file (`backend/data/bundles/`). Only if
neither exists does it run a live Deepfire simulation (minutes), pull register
assets from Postgres and named facilities from OpenStreetMap, and record the
result. The engine ranks assets and tests how stable the ranking is. The
briefing service turns the top results into a trilingual briefing via the LLM,
checked by a validator, with templates as the fallback.

Notes:

- `GET /assets` is the shared contract endpoint; it reads Postgres directly and
  is separate from the decision flow.
- `GET /fire/arrival-grid` (Deepfire exposed directly) is omitted for brevity.
- The template fallback is inferred from `briefing/templates.py` sitting beside
  `llm.py`.
