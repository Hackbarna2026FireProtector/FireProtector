"""Extract the public forests of Catalonia (INSPIRE theme AM, Area management/
restriction/regulation zones) into the CSV loaded into protection.forest_areas.

Input is the GeoJSON FeatureCollection served by the Catalan INSPIRE OGC API -
Features endpoint, one of the two access points on the dataset's metadata
record. The other one, the ATOM/GML download, carries only the harmonised
INSPIRE core -- not the forest attributes (public-utility catalogue number,
management plan, certification) that the GeoJSON exposes.

Coordinates are ETRS89 geographic (EPSG:4258), which within a metre is WGS84.
"""
import csv, json, random, sys
from math import cos, radians

from shapely.geometry import Polygon, shape

# Mean Earth radius (IUGG), as in app/geo.py.
EARTH_RADIUS_M = 6_371_008.8

# Order matters: setup_db.sh COPYs with HEADER MATCH, so these names and this
# order must equal the columns of protection.forest_areas.
FIELDS = [
    "forest_id", "name", "cup_code", "elenc_code",
    "has_agreement", "has_management_plan", "certification", "area_ha",
    "latitude", "longitude",
    "min_latitude", "max_latitude", "min_longitude", "max_longitude",
    "version_id", "geometry", "vulnerability",
]


def _clean(value):
    """Both the empty string and the source's literal "No" mean "not set"."""
    return value if value not in (None, "", "No") else None


def _project(ring):
    """Sinusoidal projection of a lon/lat ring, in metres.

    Sinusoidal is equal-area, so a plain planar area over the projected ring is
    the real area on the sphere. The rings carry hundreds of vertices, so the
    straight segments between them differ from the projected curve by far less
    than the source's own precision.
    """
    return [
        (radians(lon) * EARTH_RADIUS_M * cos(radians(lat)), radians(lat) * EARTH_RADIUS_M)
        for lon, lat in ring
    ]


def _area_ha(geom):
    """Area of a (multi)polygon in hectares."""
    parts = geom.geoms if hasattr(geom, "geoms") else [geom]
    m2 = sum(
        Polygon(_project(p.exterior.coords), [_project(r.coords) for r in p.interiors]).area
        for p in parts
    )
    return m2 / 10_000


def extract(collection):
    for feature in collection["features"]:
        p = feature["properties"]
        geom = shape(feature["geometry"])

        # representative_point == ST_PointOnSurface: always inside the forest,
        # unlike the centroid on a ring-shaped or multi-part one.
        point = geom.representative_point()
        min_lon, min_lat, max_lon, max_lat = geom.bounds

        yield {
            "forest_id":           p["localid"],
            "name":                p["name_text"],
            "cup_code":            _clean(p["forest_cup"]),
            "elenc_code":          _clean(p["forest_elenc"]),
            "has_agreement":       "true" if p["forest_conveni"] else "false",
            "has_management_plan": "true" if p["forest_ordenacio"] else "false",
            "certification":       _clean(p["forest_certificacio"]),
            "area_ha":             round(_area_ha(geom), 2),
            "latitude":            round(point.y, 7),
            "longitude":           round(point.x, 7),
            "min_latitude":        round(min_lat, 7),
            "max_latitude":        round(max_lat, 7),
            "min_longitude":       round(min_lon, 7),
            "max_longitude":       round(max_lon, 7),
            "version_id":          p.get("versionid"),
            "geometry":            json.dumps(feature["geometry"], separators=(",", ":")),
            # Placeholder with the right shape, not a risk model. The column
            # has the same default, which covers rows inserted by hand.
            "vulnerability":       round(random.random(), 6),
        }


if __name__ == "__main__":
    w = csv.DictWriter(sys.stdout, FIELDS)
    w.writeheader()

    n = 0
    for path in sys.argv[1:] or ["/dev/stdin"]:
        with open(path, encoding="utf-8") as fh:
            collection = json.load(fh)

        # The service pages its answer. A short page means the caller's `limit`
        # was capped, so stop before writing anything rather than load a
        # silently partial dataset.
        matched = collection.get("numberMatched")
        if matched is not None and matched != len(collection["features"]):
            sys.exit(
                f"{path}: got {len(collection['features'])} of {matched} features -- "
                f"the service capped the page size; page through it instead."
            )

        for row in extract(collection):
            w.writerow(row)
            n += 1

    print(f"{n} forests", file=sys.stderr)
