"""SQL for reading and writing asset rows."""

from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection, sql

from .config import Settings
from .geo import BoundingBox
from .payload import Column


def _table_identifier(table: str) -> sql.Identifier:
    """Accept either "table" or "schema.table" and quote each part."""
    return sql.Identifier(*table.split("."))


def _longitude_clause(column: sql.Identifier, bbox: BoundingBox) -> tuple[sql.Composed, list[float]]:
    """OR-ed BETWEEN clauses, so a box crossing the antimeridian still works."""
    parts: list[sql.Composed] = []
    params: list[float] = []
    for low, high in bbox.lon_ranges:
        parts.append(sql.SQL("{col} BETWEEN %s AND %s").format(col=column))
        params.extend([low, high])
    return sql.SQL("({})").format(sql.SQL(" OR ").join(parts)), params


async def fetch_buildings_in_box(
    conn: AsyncConnection,
    settings: Settings,
    bbox: BoundingBox,
    center_latitude: float,
    center_longitude: float,
    limit: int,
) -> list[dict[str, Any]]:
    """Every row whose point falls inside `bbox`, nearest to the centre first.

    All columns are returned as-is, so the endpoint keeps working when the
    building dataset gains or loses attribute columns.
    """
    table = _table_identifier(settings.asset_specs_table)
    lat_col = sql.Identifier(settings.latitude_column)
    lon_col = sql.Identifier(settings.longitude_column)

    lon_clause, lon_params = _longitude_clause(lon_col, bbox)

    # Planar approximation of distance to the centre: fine for ordering within a
    # box of a few km, and it avoids requiring PostGIS.
    order_by = sql.SQL(
        "(({lat} - %s) * ({lat} - %s)) + "
        "(({lon} - %s) * ({lon} - %s) * cos(radians(%s)) * cos(radians(%s)))"
    ).format(lat=lat_col, lon=lon_col)

    query = sql.SQL(
        "SELECT * FROM {table} "
        "WHERE {lat} BETWEEN %s AND %s AND {lon_clause} "
        "ORDER BY {order_by} ASC "
        "LIMIT %s"
    ).format(table=table, lat=lat_col, lon_clause=lon_clause, order_by=order_by)

    params: list[Any] = [bbox.min_latitude, bbox.max_latitude]
    params.extend(lon_params)
    params.extend(
        [
            center_latitude,
            center_latitude,
            center_longitude,
            center_longitude,
            center_latitude,
            center_latitude,
        ]
    )
    params.append(limit)

    async with conn.cursor() as cur:
        await cur.execute(query, params)
        return await cur.fetchall()


async def fetch_table_columns(conn: AsyncConnection, settings: Settings) -> dict[str, Column]:
    """The table's columns in declaration order, or empty if it does not exist.

    Read from the catalog so the API can validate a POST body against the real
    table instead of a hard-coded idea of what a building looks like.
    """
    qualified = _table_identifier(settings.asset_specs_table).as_string(conn)

    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT attname, attidentity, attgenerated "
            "FROM pg_attribute "
            "WHERE attrelid = to_regclass(%s) AND attnum > 0 AND NOT attisdropped "
            "ORDER BY attnum",
            [qualified],
        )
        rows = await cur.fetchall()

    return {
        row["attname"]: Column(
            name=row["attname"],
            # GENERATED ALWAYS AS IDENTITY ('a') and stored generated columns
            # ('s') are filled in by the database and must not be supplied.
            insertable=row["attidentity"] != "a" and row["attgenerated"] == "",
        )
        for row in rows
    }


async def insert_buildings(
    conn: AsyncConnection,
    settings: Settings,
    rows: list[dict[str, Any]],
    column_order: list[str],
) -> list[dict[str, Any]]:
    """Insert every row in one statement and return them as stored.

    A row that omits one of `column_order` gets DEFAULT for it, so callers can
    send partial rows without having to know the table's defaults.
    """
    table = _table_identifier(settings.asset_specs_table)

    value_groups: list[sql.Composed] = []
    params: list[Any] = []
    for row in rows:
        placeholders: list[sql.Composable] = []
        for column in column_order:
            if column in row:
                placeholders.append(sql.Placeholder())
                params.append(row[column])
            else:
                placeholders.append(sql.SQL("DEFAULT"))
        value_groups.append(sql.SQL("({})").format(sql.SQL(", ").join(placeholders)))

    query = sql.SQL("INSERT INTO {table} ({columns}) VALUES {values} RETURNING *").format(
        table=table,
        columns=sql.SQL(", ").join(sql.Identifier(c) for c in column_order),
        values=sql.SQL(", ").join(value_groups),
    )

    async with conn.cursor() as cur:
        await cur.execute(query, params)
        return await cur.fetchall()


def _bbox_predicates(
    settings: Settings, bbox: BoundingBox
) -> tuple[sql.Composed, list[float], sql.SQL, list[float]]:
    """WHERE clauses for the two tables /assets reads, with their parameters.

    Points are tested by containment, forests by envelope overlap: a forest
    counts as being in the box when any part of it is, not only its centre.
    """
    point_where = sql.SQL("{lat} BETWEEN %s AND %s AND {lon} BETWEEN %s AND %s").format(
        lat=sql.Identifier(settings.latitude_column),
        lon=sql.Identifier(settings.longitude_column),
    )
    point_params = [
        bbox.min_latitude, bbox.max_latitude, bbox.min_longitude, bbox.max_longitude
    ]

    # Column names on the forest table are fixed by db/init/02_forests.sql.
    forest_where = sql.SQL(
        "max_latitude >= %s AND min_latitude <= %s "
        "AND max_longitude >= %s AND min_longitude <= %s"
    )
    forest_params = [
        bbox.min_latitude, bbox.max_latitude, bbox.min_longitude, bbox.max_longitude
    ]

    return point_where, point_params, forest_where, forest_params


async def count_assets_in_bbox(
    conn: AsyncConnection, settings: Settings, bbox: BoundingBox
) -> int:
    """How many features the box holds in total, across both tables."""
    assets = _table_identifier(settings.asset_specs_table)
    forests = _table_identifier(settings.forest_areas_table)
    point_where, point_params, forest_where, forest_params = _bbox_predicates(settings, bbox)

    query = sql.SQL(
        "SELECT (SELECT count(*) FROM {assets} WHERE {point_where}) "
        "     + (SELECT count(*) FROM {forests} WHERE {forest_where}) AS n"
    ).format(
        assets=assets, forests=forests, point_where=point_where, forest_where=forest_where
    )

    async with conn.cursor() as cur:
        await cur.execute(query, point_params + forest_params)
        row = await cur.fetchone()
        return int(row["n"])


async def fetch_assets_in_bbox(
    conn: AsyncConnection,
    settings: Settings,
    bbox: BoundingBox,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    """One page of assets in the box: point assets and forest polygons together.

    Ordered by the identifier that goes on the wire, which is what makes
    offset paging stable -- without a total order a page can repeat or skip
    rows. The order is lexical, so every point precedes every forest.
    """
    assets = _table_identifier(settings.asset_specs_table)
    forests = _table_identifier(settings.forest_areas_table)
    point_where, point_params, forest_where, forest_params = _bbox_predicates(settings, bbox)

    query = sql.SQL(
        "SELECT 'asset-' || asset_id AS wire_id, asset_type, name, value, source, "
        "       jsonb_build_object('type', 'Point', 'coordinates', "
        "                          jsonb_build_array({lon}, {lat})) AS geometry "
        "FROM {assets} WHERE {point_where} "
        "UNION ALL "
        # Forests carry no value or source of their own; both are constants.
        "SELECT 'forest-' || forest_id, 'forest', name, 1, 'INSPIRE', geometry "
        "FROM {forests} WHERE {forest_where} "
        "ORDER BY wire_id LIMIT %s OFFSET %s"
    ).format(
        assets=assets,
        forests=forests,
        point_where=point_where,
        forest_where=forest_where,
        lat=sql.Identifier(settings.latitude_column),
        lon=sql.Identifier(settings.longitude_column),
    )

    async with conn.cursor() as cur:
        await cur.execute(query, point_params + forest_params + [limit, offset])
        return await cur.fetchall()
