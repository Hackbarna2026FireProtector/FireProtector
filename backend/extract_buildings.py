"""Extract building, building_type, location_lat, location_long, municipality_id
from the INSPIRE `inspire-edificis` GML files (Catalonia, bu-core2d 4.0).

The GML carries no municipality attribute -- the municipality is encoded as a
slug inside base:localId (`ID.BU.<slug>.<uuid>`), so we join it to the INE code
through municipality_slug_map.csv.
"""
import csv, sys, os
from lxml import etree
from shapely.geometry import Polygon, MultiPolygon

B  = "{http://inspire.ec.europa.eu/schemas/bu-core2d/4.0}Building"
BB = "{http://inspire.ec.europa.eu/schemas/bu-base/4.0}"
BA = "{http://inspire.ec.europa.eu/schemas/base/3.3}"
G  = "{http://www.opengis.net/gml/3.2}"
XL = "{http://www.w3.org/1999/xlink}href"

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "data", "municipality_slug_map.csv"), encoding="utf-8") as fh:
    SLUG2INE = {r["slug"]: r["ine"] for r in csv.DictReader(fh)}  # 5-digit INE


def _code(el):
    """Last path segment of an INSPIRE codelist URI; None when xsi:nil."""
    return el.get(XL).rsplit("/", 1)[-1] if el is not None and el.get(XL) else None


def _ring(posList):
    """GML EPSG:4258 posList is 'lat lon lat lon ...' -> [(lon, lat), ...]."""
    v = [float(x) for x in posList.text.split()]
    return list(zip(v[1::2], v[0::2]))


def extract(gml_path):
    for _, f in etree.iterparse(gml_path, events=("end",), tag=B):
        polys = []
        for patch in f.iter(G + "PolygonPatch"):
            shell = _ring(patch.find(f"{G}exterior/{G}LinearRing/{G}posList"))
            holes = [_ring(p) for p in
                     patch.findall(f"{G}interior/{G}LinearRing/{G}posList")]
            polys.append(Polygon(shell, holes))

        # representative_point == ST_PointOnSurface: always inside the footprint,
        # unlike the centroid on L-shaped or holed buildings.
        pt = MultiPolygon(polys).representative_point()

        local_id = f.findtext(f"{BB}inspireId/{BA}Identifier/{BA}localId")
        slug = local_id.split(".")[2]

        yield {
            "building":        local_id,
            "building_type":   _code(f.find(BB + "buildingNature")),
            "location_lat":    round(pt.y, 7),
            "location_long":   round(pt.x, 7),
            "municipality_id": SLUG2INE[slug],
        }

        f.clear()
        while f.getprevious() is not None:
            del f.getparent()[0]


if __name__ == "__main__":
    w = csv.DictWriter(sys.stdout, ["building", "building_type",
                                    "location_lat", "location_long",
                                    "municipality_id"])
    w.writeheader()
    for path in sys.argv[1:]:
        for row in extract(path):
            w.writerow(row)
