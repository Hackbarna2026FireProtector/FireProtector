"""Critical facilities from OpenStreetMap.

This is where every *named* asset in the ranking comes from. The INSPIRE
register has millions of rows and no names — it can say how many buildings a
fire reaches, never which ones — so the hospitals, schools, substations, care
homes, water plants, telecom towers and fuel stations the ranked list shows are
queried here instead.

Uses osmnx to query the tag set from spec §6.4, maps features to asset types,
and assigns ``value``/``vulnerability`` from ``data/asset_types.yaml``.
``asset_id`` is derived from the OSM element so it is stable across runs.

Overpass is a live third-party service and this is the one hard dependency on
it. Nothing is cached here: a scenario's facilities are captured inside its
persisted bundle, so a bundle on disk means the ranking still renders when
Overpass is unreachable.
"""

from __future__ import annotations

from typing import Any

from app.engine.contracts import Asset, parse_assets
from app.providers.asset_types import asset_type_defaults
from app.providers.base import AssetProvider, BBox, ProviderError, _StatusMixin

# Spec §6.4 tag set (extensions to be recorded in DECISIONS.md).
TAG_QUERY: dict[str, bool | str | list[str]] = {
    "amenity": [
        "hospital",
        "clinic",
        "school",
        "kindergarten",
        "college",
        "university",
        "social_facility",
        "fuel",
    ],
    "power": ["substation"],
    "man_made": ["water_works", "wastewater_plant", "mast", "tower"],
}

_AMENITY_MAP = {
    "hospital": "hospital",
    "clinic": "clinic",
    "school": "school",
    "kindergarten": "school",
    "college": "school",
    "university": "school",
    "social_facility": "care_home",
    "fuel": "fuel_station",
}
_MAN_MADE_MAP = {
    "water_works": "water_plant",
    "wastewater_plant": "water_plant",
    "mast": "telecom_tower",
    "tower": "telecom_tower",
}


def _asset_type(tags: dict[str, Any]) -> str | None:
    """Map OSM tags to an asset type; ``None`` skips the feature."""
    amenity = tags.get("amenity")
    if amenity in _AMENITY_MAP:
        return _AMENITY_MAP[amenity]
    if tags.get("power") == "substation":
        return "substation"
    man_made = tags.get("man_made")
    if man_made in ("water_works", "wastewater_plant"):
        return "water_plant"
    if man_made in ("mast", "tower"):
        # Spec: telecom towers are "mast|tower with communication tags" —
        # skip bare powerline towers (recorded in DECISIONS.md).
        comm_keys = [k for k in tags if k.startswith("communication") or k == "tower:type"]
        comm_vals = {"communication", "cellular", "microwave", "mobile_phone"}
        if any(
            str(tags.get(k, "")).split(";")[0] in comm_vals or k.startswith("communication")
            for k in comm_keys
        ):
            return "telecom_tower"
        return None
    return None


def features_to_payload(gdf: Any) -> dict[str, Any]:
    """Convert an osmnx GeoDataFrame to the asset contract payload."""
    defaults = asset_type_defaults()
    features: list[dict[str, Any]] = []
    for idx, row in gdf.iterrows():
        element, osmid = idx if isinstance(idx, tuple) else ("element", idx)
        tags = {k: v for k, v in row.items() if isinstance(v, str)}
        asset_type = _asset_type(tags)
        if asset_type is None:
            continue
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        if geom.geom_type not in ("Point", "Polygon", "MultiPolygon"):
            geom = geom.centroid  # lines/relations -> representative point
        table = defaults["types"].get(asset_type, {})
        features.append(
            {
                "type": "Feature",
                "geometry": geom.__geo_interface__,
                "properties": {
                    "asset_id": f"osm-{element}-{osmid}",
                    "asset_type": asset_type,
                    "name": tags.get("name", f"{asset_type} {osmid}"),
                    "value": table.get("value", defaults["defaults"]["value"]),
                    "vulnerability": table.get(
                        "vulnerability", defaults["defaults"]["vulnerability"]
                    ),
                    "source": "osm",
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


# Overpass mirrors, tried in order. osmnx uses only the first, which is a
# single point of failure: verified 2026-09-20 that overpass-api.de refused
# TCP/443 outright from one network, taking the entire named layer with it.
#
# Every entry must carry PLANET-WIDE data. Regional mirrors are deliberately
# excluded, and this is not fussiness: overpass.osm.ch is reachable when the
# others are not, and answers a Barcelona query with `total: 0` and HTTP 200 —
# indistinguishable from "there is no hospital here". A mirror with the wrong
# extract does not fail, it lies, and the ranking would quietly lose every
# named asset while looking entirely healthy.
#
# Override with OVERPASS_URLS (JSON array) to pin a mirror.
DEFAULT_ENDPOINTS: tuple[str, ...] = (
    "https://overpass-api.de/api",
    "https://overpass.kumi.systems/api",
    "https://overpass.private.coffee/api",
)


class OsmAssetProvider(AssetProvider):
    """Critical facilities from OpenStreetMap via osmnx."""

    def __init__(
        self,
        timeout_s: float = 30.0,
        endpoints: tuple[str, ...] | list[str] | None = None,
    ) -> None:
        _StatusMixin.__init__(self, "live-osm")
        self.timeout_s = timeout_s
        self.endpoints = tuple(endpoints) if endpoints else DEFAULT_ENDPOINTS

    def get_assets(self, bbox: BBox) -> list[Asset]:
        try:
            import osmnx as ox
        except ImportError as exc:  # pragma: no cover - dependency is pinned
            raise ProviderError("osmnx not installed") from exc

        from osmnx._errors import InsufficientResponseError

        errors: list[str] = []
        for endpoint in self.endpoints:
            ox.settings.overpass_url = endpoint
            ox.settings.requests_timeout = int(self.timeout_s)
            try:
                # osmnx 2.x signature: features_from_bbox(bbox, tags) with
                # bbox = (left, bottom, right, top) in EPSG:4326.
                gdf = ox.features.features_from_bbox(bbox, TAG_QUERY)
            except InsufficientResponseError:
                # The mirror answered and there is simply nothing tagged here.
                # A rural burn area with no hospital in it is a real result,
                # not a failure, and must not send us to the next mirror.
                self.status.source = f"live-osm ({endpoint})"
                return []
            except Exception as exc:  # noqa: BLE001 - try the next mirror
                errors.append(f"{endpoint}: {exc}")
                continue
            self.status.source = f"live-osm ({endpoint})"
            return parse_assets(features_to_payload(gdf))

        raise ProviderError("OSM query failed on every mirror — " + "; ".join(errors))
