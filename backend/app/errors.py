"""Turn database errors into HTTP responses that say what to do about them."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from fastapi import HTTPException

from .config import Settings

logger = logging.getLogger(__name__)


def missing_table(settings: Settings) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=(
            f"Table '{settings.building_specs_table}' with columns "
            f"'{settings.latitude_column}'/'{settings.longitude_column}' was not found "
            "in the database. Load the building dataset, or point "
            "BUILDING_SPECS_TABLE / LATITUDE_COLUMN / LONGITUDE_COLUMN at it."
        ),
    )


def _diagnostic(exc: psycopg.Error) -> str:
    """The primary message plus, when present, the constraint that failed."""
    parts = [exc.diag.message_primary or str(exc)]
    if exc.diag.constraint_name:
        parts.append(f"(constraint: {exc.diag.constraint_name})")
    if exc.diag.message_detail:
        parts.append(exc.diag.message_detail)
    return " ".join(parts)


@contextmanager
def translate_db_errors(settings: Settings) -> Iterator[None]:
    """Map psycopg failures onto meaningful status codes for both routes."""
    try:
        yield
    except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn) as exc:
        logger.warning("building data not queryable: %s", exc)
        raise missing_table(settings) from exc
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(status_code=409, detail=_diagnostic(exc)) from exc
    except (
        psycopg.errors.NotNullViolation,
        psycopg.errors.CheckViolation,
        psycopg.errors.ForeignKeyViolation,
        psycopg.errors.InvalidTextRepresentation,
        psycopg.errors.NumericValueOutOfRange,
        psycopg.errors.DatatypeMismatch,
        psycopg.errors.StringDataRightTruncation,
    ) as exc:
        raise HTTPException(status_code=400, detail=_diagnostic(exc)) from exc
    except psycopg.OperationalError as exc:
        logger.exception("database unavailable")
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}") from exc
