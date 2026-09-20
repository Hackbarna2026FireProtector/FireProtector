"""OSM asset fallback tests — mapping logic with a fake osmnx result."""

from __future__ import annotations

import geopandas as gpd
from shapely.geometry import Point

from app.providers.osm_assets import _asset_type, features_to_payload


def _gdf(rows: list[dict]) -> gpd.GeoDataFrame:
    import pandas as pd

    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    gdf.index = pd.MultiIndex.from_tuples(
        [("node", 1000 + i) for i in range(len(rows))], names=["element", "osmid"]
    )
    return gdf


def test_asset_type_mapping() -> None:
    assert _asset_type({"amenity": "hospital"}) == "hospital"
    assert _asset_type({"amenity": "kindergarten"}) == "school"
    assert _asset_type({"amenity": "social_facility"}) == "care_home"
    assert _asset_type({"amenity": "fuel"}) == "fuel_station"
    assert _asset_type({"power": "substation"}) == "substation"
    assert _asset_type({"man_made": "water_works"}) == "water_plant"
    # Bare towers (powerline) are skipped; communication towers kept.
    assert _asset_type({"man_made": "tower"}) is None
    assert _asset_type({"man_made": "tower", "tower:type": "communication"}) == "telecom_tower"
    assert _asset_type({"man_made": "mast", "communication:mobile_phone": "yes"}) == "telecom_tower"
    assert _asset_type({"amenity": "restaurant"}) is None


def test_features_to_payload() -> None:
    gdf = _gdf(
        [
            {
                "geometry": Point(1.25, 41.8),
                "amenity": "hospital",
                "name": "Hospital de Cervera",
            },
            {
                "geometry": Point(1.26, 41.81),
                "power": "substation",
                "name": "Subestació",
            },
            {
                "geometry": Point(1.27, 41.82),
                "amenity": "restaurant",  # skipped
                "name": "Bar",
            },
        ]
    )
    payload = features_to_payload(gdf)
    assert len(payload["features"]) == 2
    ids = {f["properties"]["asset_id"] for f in payload["features"]}
    assert all(i.startswith("osm-node-") for i in ids)
    hospital = payload["features"][0]["properties"]
    assert hospital["asset_type"] == "hospital"
    assert hospital["value"] > 0 and hospital["source"] == "osm"


def test_provider_end_to_end_with_stubbed_osmnx(monkeypatch) -> None:
    import osmnx as ox

    gdf = _gdf([{"geometry": Point(1.25, 41.8), "amenity": "clinic", "name": "CAP"}])
    monkeypatch.setattr(ox.features, "features_from_bbox", lambda bbox, tags: gdf)

    from app.providers.osm_assets import OsmAssetProvider

    assets = OsmAssetProvider().get_assets((1.0, 41.6, 1.6, 42.0))
    assert len(assets) == 1
    assert assets[0].asset_type == "clinic"
