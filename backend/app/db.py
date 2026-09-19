"""Connection pool for the Neon Postgres database."""

from __future__ import annotations

from fastapi import Request
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import JsonbBinaryDumper, JsonbDumper
from psycopg.types.numeric import FloatLoader
from psycopg_pool import AsyncConnectionPool

from .config import Settings


async def _configure(conn: AsyncConnection) -> None:
    """Per-connection type handling."""
    # Numeric/decimal columns come back as JSON numbers rather than strings.
    conn.adapters.register_loader("numeric", FloatLoader)
    # A JSON object in a request body can be written straight to a json/jsonb
    # column. Lists are left alone so they still map to Postgres arrays.
    conn.adapters.register_dumper(dict, JsonbDumper)
    conn.adapters.register_dumper(dict, JsonbBinaryDumper)


def create_pool(settings: Settings) -> AsyncConnectionPool:
    """Build the pool. It is opened during application startup, not here."""
    return AsyncConnectionPool(
        conninfo=settings.database_url,
        min_size=settings.pool_min_size,
        max_size=settings.pool_max_size,
        kwargs={"row_factory": dict_row},
        configure=_configure,
        open=False,
    )


def get_pool(request: Request) -> AsyncConnectionPool:
    """FastAPI dependency: the pool created at startup."""
    return request.app.state.pool
