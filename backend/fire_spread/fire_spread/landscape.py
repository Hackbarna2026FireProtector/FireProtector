"""Static landscape tier: window-read the Catalonia-wide 50 m COGs into ELMFIRE inputs.

Layers (all Int16, EPSG:25831, identical grids) live in ``DATA_DIR``:
dem (m), slp (deg), asp (deg), fbfm40 (Scott & Burgan code), cc (%),
ch (10·m), cbh (10·m), cbd (100·kg/m³). ``manifest.json`` describes provenance.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.windows import Window

from .models import Ignition, OutsideCoverage
from .rasters import NODATA, grid_transform, write_raster

CRS = "EPSG:25831"
LAYERS = ("dem", "slp", "asp", "fbfm40", "cc", "ch", "cbh", "cbd")
BARRIER = "barrier"  # optional Float32 layer: width (m) of roads/rivers crossing the cell
AGRI = "agri"  # optional Byte layer from OSM landuse: 1 = orchard/vineyard/greenhouse, 2 = farmland
AGRI_FUEL = 104  # ZAFM maps all agriculture to GR4
AGRI_WOODY_FUEL = 93  # NB3 "agricultural": orchards/vineyards/olive groves carry no continuous surface fuel
NON_BURNABLE = frozenset(range(91, 100))  # NB1..NB9: urban, snow, agriculture, water, barren

_to_utm = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)
_to_wgs = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)


def lonlat_to_xy(lon: float, lat: float) -> tuple[float, float]:
    return _to_utm.transform(lon, lat)


def xy_to_lonlat(x: float, y: float) -> tuple[float, float]:
    return _to_wgs.transform(x, y)


@dataclass(frozen=True)
class Domain:
    """Square simulation domain on the static grid (lower-left corner + n cells)."""

    xll: float
    yll: float
    n: int
    cellsize: float

    @property
    def xur(self) -> float:
        return self.xll + self.n * self.cellsize

    @property
    def yur(self) -> float:
        return self.yll + self.n * self.cellsize

    @property
    def transform(self):
        return grid_transform(self.xll, self.yll, self.n, self.cellsize)


def domain_for(
    x: float,
    y: float,
    size_m: float,
    cellsize: float,
    downwind: tuple[float, float] | None = None,
    ignition_frac: float = 0.5,
) -> Domain:
    """Square domain of ``size_m`` containing (x, y), snapped to multiples of ``cellsize``.

    With ``downwind`` (unit vector the wind blows *towards*) the domain is shifted so the
    ignition sits ``ignition_frac`` of the way from the upwind edge along that axis —
    fires run downwind, so a centred domain wastes half its cells. ``ignition_frac=0.5``
    or no wind = centred.
    """
    n = int(round(size_m / cellsize))
    cx, cy = x, y
    if downwind is not None and ignition_frac != 0.5:
        ux, uy = downwind
        shift = (0.5 - ignition_frac) * size_m
        cx, cy = x + ux * shift, y + uy * shift
    xll = math.floor((cx - size_m / 2) / cellsize) * cellsize
    yll = math.floor((cy - size_m / 2) / cellsize) * cellsize
    return Domain(xll, yll, n, cellsize)


# Recently burned areas: fuel is gone for a couple of seasons, then grass/low shrub returns.
BURN_BARE_YEARS = 2       # age < 2 y -> non-burnable (NB9)
BURN_REGROWTH_YEARS = 6   # 2 <= age < 6 y and shrub/timber fuel -> GR2 (102)
REGROWTH_FUEL = 102


def apply_agriculture(fbfm: np.ndarray, agri: np.ndarray) -> np.ndarray:
    """Orchards, vineyards, olive groves and greenhouses (OSM landuse) are non-burnable
    agriculture (NB3) instead of ZAFM's blanket GR4; cereal/other farmland keeps GR4 (cured
    stubble in the Mediterranean fuel set). Pure function."""
    out = fbfm.copy()
    out[(fbfm == AGRI_FUEL) & (agri == 1)] = AGRI_WOODY_FUEL
    return out


def apply_recent_burns(fbfm: np.ndarray, burn_year: np.ndarray, now_year: int, min_age: int = 0) -> np.ndarray:
    """Remap fuel where a DARP fire perimeter burned recently. ``burn_year`` holds the
    latest burn year per cell (NODATA/0 = never). ``min_age`` = 1 ignores burns of the
    ignition year itself (hindcasts: the fire being simulated is in the raster). Pure
    function; returns a new array."""
    out = fbfm.copy()
    valid = (burn_year > 0) & (burn_year != NODATA) & (fbfm != NODATA)
    age = now_year - burn_year
    valid &= age >= min_age
    bare = valid & (age >= 0) & (age < BURN_BARE_YEARS)
    regrow = valid & (age >= BURN_BARE_YEARS) & (age < BURN_REGROWTH_YEARS) & (fbfm >= 141) & (fbfm <= 189)
    out[bare] = 99
    out[regrow] = REGROWTH_FUEL
    return out


@dataclass
class LandscapeWindow:
    domain: Domain
    layers: dict[str, np.ndarray]  # Int16 arrays (n, n), NODATA where outside coverage
    coverage: np.ndarray  # bool (n, n)
    barrier: np.ndarray | None = None  # Float32 (n, n) barrier width in m, 0 = none

    def fbfm_at(self, x: float, y: float) -> int:
        col = int((x - self.domain.xll) // self.domain.cellsize)
        row = int((self.domain.yur - y) // self.domain.cellsize)
        return int(self.layers["fbfm40"][row, col])


class Landscape:
    """Reader over the static COGs. Cheap to construct; opens files per read."""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.manifest = self._load_manifest()
        with rasterio.open(self.data_dir / "dem.tif") as src:
            self.transform = src.transform
            self.width, self.height = src.width, src.height
            self.cellsize = float(src.res[0])
            self.bounds = src.bounds

    def _load_manifest(self) -> dict:
        p = self.data_dir / "manifest.json"
        if p.exists():
            return json.loads(p.read_text())
        return {}

    def contains(self, x: float, y: float) -> bool:
        b = self.bounds
        return b.left <= x < b.right and b.bottom <= y < b.top

    @property
    def has_barriers(self) -> bool:
        return (self.data_dir / f"{BARRIER}.tif").exists()

    def read_window(self, domain: Domain, now_year: int | None = None, barriers: bool = False,
                    burn_min_age: int = 0) -> LandscapeWindow:
        if domain.cellsize != self.cellsize:
            raise ValueError(f"domain cellsize {domain.cellsize} != static grid {self.cellsize}")
        col0 = (domain.xll - self.transform.c) / self.cellsize
        row0 = (self.transform.f - domain.yur) / self.cellsize
        if abs(col0 - round(col0)) > 1e-6 or abs(row0 - round(row0)) > 1e-6:
            raise ValueError("domain is not aligned to the static grid")
        win = Window(int(round(col0)), int(round(row0)), domain.n, domain.n)
        layers: dict[str, np.ndarray] = {}
        for name in LAYERS:
            with rasterio.open(self.data_dir / f"{name}.tif") as src:
                arr = src.read(1, window=win, boundless=True, fill_value=NODATA)
                nod = src.nodata
            if nod is not None and nod != NODATA:
                arr = np.where(arr == nod, NODATA, arr)
            layers[name] = arr.astype(np.int16)
        coverage = layers["fbfm40"] != NODATA
        agri_path = self.data_dir / f"{AGRI}.tif"
        if agri_path.exists():
            with rasterio.open(agri_path) as src:
                agri = src.read(1, window=win, boundless=True, fill_value=0)
            layers["fbfm40"] = apply_agriculture(layers["fbfm40"], agri)
        burn_path = self.data_dir / "burnyear.tif"
        if now_year is not None and burn_path.exists():
            with rasterio.open(burn_path) as src:
                burn_year = src.read(1, window=win, boundless=True, fill_value=0)
            layers["fbfm40"] = apply_recent_burns(layers["fbfm40"], burn_year, now_year, burn_min_age)
        barrier = None
        if barriers and self.has_barriers:
            with rasterio.open(self.data_dir / f"{BARRIER}.tif") as src:
                barrier = src.read(1, window=win, boundless=True, fill_value=0).astype(np.float32)
                if src.nodata is not None:
                    barrier[barrier == src.nodata] = 0.0
        return LandscapeWindow(domain, layers, coverage, barrier)


def check_ignition(win: LandscapeWindow, x: float, y: float) -> None:
    """422 if the ignition cell has no data or a non-burnable fuel model."""
    if not (win.domain.xll <= x < win.domain.xur and win.domain.yll <= y < win.domain.yur):
        raise OutsideCoverage("ignition outside the simulation domain")
    code = win.fbfm_at(x, y)
    if code == NODATA:
        raise OutsideCoverage("ignition outside static data coverage (Catalonia)")
    if code in NON_BURNABLE:
        raise OutsideCoverage(f"ignition on a non-burnable cell (FBFM40 {code}: urban/water/agriculture/barren)")


def write_inputs(win: LandscapeWindow, out_dir: Path, adj: float = 1.0) -> None:
    """Write the 8 static Int16 layers + adj/phi Float32 rasters for ELMFIRE. ``adj`` is the
    uniform spread-rate multiplier (calibration)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tr = win.domain.transform
    for name, arr in win.layers.items():
        # ELMFIRE does no nodata handling: feed non-burnable fuel / flat terrain instead of -9999.
        fill = 99 if name == "fbfm40" else 0
        write_raster(out_dir / f"{name}.tif", np.where(arr == NODATA, fill, arr).astype(np.int16), tr, CRS, "int16")
    ones = np.ones((win.domain.n, win.domain.n), dtype=np.float32)
    write_raster(out_dir / "adj.tif", ones * np.float32(adj), tr, CRS, "float32")
    write_raster(out_dir / "phi.tif", ones, tr, CRS, "float32")
    if win.barrier is not None:
        write_raster(out_dir / f"{BARRIER}.tif", win.barrier, tr, CRS, "float32", nodata=None)


class SyntheticLandscape:
    """Flat, uniform-fuel landscape anywhere (integration tests, no real data needed)."""

    def __init__(self, fbfm: int = 102, slope_deg: int = 0, cellsize: float = 50.0,
                 barrier: tuple[float, float] | None = None):
        """``barrier`` = (x, width_m): a north-south fire break of that width at easting x."""
        self.fbfm, self.slope_deg, self.cellsize = fbfm, slope_deg, cellsize
        self.barrier_spec = barrier
        self.manifest = {"synthetic": True, "fbfm40": fbfm}

    @property
    def has_barriers(self) -> bool:
        return self.barrier_spec is not None

    def contains(self, x: float, y: float) -> bool:
        return True

    def read_window(self, domain: Domain, now_year: int | None = None, barriers: bool = False,
                    burn_min_age: int = 0) -> LandscapeWindow:
        n = domain.n
        layers = {
            "dem": np.zeros((n, n), np.int16),
            "slp": np.full((n, n), self.slope_deg, np.int16),
            "asp": np.zeros((n, n), np.int16),
            "fbfm40": np.full((n, n), self.fbfm, np.int16),
            "cc": np.zeros((n, n), np.int16),
            "ch": np.zeros((n, n), np.int16),
            "cbh": np.zeros((n, n), np.int16),
            "cbd": np.zeros((n, n), np.int16),
        }
        barrier = None
        if barriers and self.barrier_spec is not None:
            bx, width = self.barrier_spec
            barrier = np.zeros((n, n), np.float32)
            col = int((bx - domain.xll) // domain.cellsize)
            if 0 <= col < n:
                barrier[:, col] = width
        return LandscapeWindow(domain, layers, np.ones((n, n), bool), barrier)


def ignition_to_domain(
    ign: Ignition, size_m: float, cellsize: float,
    downwind: tuple[float, float] | None = None, ignition_frac: float = 0.5,
) -> tuple[float, float, Domain]:
    x, y = lonlat_to_xy(ign.lon, ign.lat)
    return x, y, domain_for(x, y, size_m, cellsize, downwind, ignition_frac)
