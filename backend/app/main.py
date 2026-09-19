"""FireProtector backend: FastAPI service over the Neon building database."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from psycopg_pool import AsyncConnectionPool

from .config import Settings, get_settings
from .db import create_pool, get_pool
from .routers import add_building, building_specs
from .schemas import HealthResponse

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.pool = create_pool(settings)
    # Does not block startup: connections are established in the background, so
    # the server comes up even while a suspended Neon compute is waking.
    await app.state.pool.open()
    try:
        yield
    finally:
        await app.state.pool.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="FireProtector API",
        description="Building data for the wildfire values-at-risk tool.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(building_specs.router)
    app.include_router(add_building.router)

    @app.get("/health", response_model=HealthResponse, tags=["meta"])
    async def health(
        pool: AsyncConnectionPool = Depends(get_pool),
        settings: Settings = Depends(get_settings),
    ) -> HealthResponse:
        try:
            async with pool.connection() as conn, conn.cursor() as cur:
                await cur.execute("SELECT 1")
                await cur.fetchone()
        except Exception as exc:  # surfaced as a status, not a 500
            return HealthResponse(status="degraded", database="unreachable", detail=str(exc))
        return HealthResponse(status="ok", database="connected")

    return app


app = create_app()
