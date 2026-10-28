import csv
import math

from pyproj import Transformer

_T = Transformer.from_crs(4326, 25832, always_xy=True)
LON = (-35.0, 45.0)
LAT = (30.0, 75.0)


def load_centroids(path):
    with open(path, newline="", encoding="utf-8") as f:
        return {r["nuts_id"]: (float(r["lon"]), float(r["lat"])) for r in csv.DictReader(f)}


def to_25832(lon, lat):
    """Validate WGS84 coordinates and project; raise ValueError if invalid."""
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (lon, lat)):
        raise ValueError("non-numeric coordinate")
    if not (LON[0] <= lon <= LON[1] and LAT[0] <= lat <= LAT[1]):
        raise ValueError(f"coordinate outside European extent: {lon},{lat}")
    x, y = _T.transform(lon, lat)
    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValueError("projection failed")
    return round(x, 2), round(y, 2)


def resolve(nuts_codes, centroids):
    """Return (x, y, status, note). Point only when exactly one NUTS-3 region is given."""
    n3 = sorted({c for c in nuts_codes if isinstance(c, str) and len(c) == 5})
    if not n3:
        return None, None, "unresolved", "country or coarse level only"
    if len(n3) > 1:
        return None, None, "ambiguous", f"multiple NUTS-3 regions: {','.join(n3)}"
    c = centroids.get(n3[0])
    if c is None:
        return None, None, "unresolved", f"no centroid for {n3[0]}"
    try:
        x, y = to_25832(*c)
    except ValueError as e:
        return None, None, "unresolved", f"invalid coordinate: {e}"
    return x, y, "resolved", f"NUTS-3 region centroid {n3[0]}"
