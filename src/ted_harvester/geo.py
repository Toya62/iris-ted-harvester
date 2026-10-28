"""NUTS-3 gazetteer lookup and EPSG:4326 -> EPSG:25832 transform. Invalid or ambiguous locations are never guessed."""
from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass
from pathlib import Path

from pyproj import Transformer

_TO_25832 = Transformer.from_crs("EPSG:4326", "EPSG:25832", always_xy=True)
NUTS_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{2,3}$")
AREA_LON = (5.5, 13.5)


class CoordinateError(ValueError):
    pass


@dataclass
class Location:
    status: str
    reason: str | None = None
    lon: float | None = None
    lat: float | None = None
    x: float | None = None
    y: float | None = None
    precision: str | None = None
    warning: str | None = None


def validate_lonlat(lon, lat) -> tuple[float, float]:
    try:
        lon, lat = float(lon), float(lat)
    except (TypeError, ValueError) as exc:
        raise CoordinateError(f"non-numeric coordinate: {lon!r}, {lat!r}") from exc
    if not (math.isfinite(lon) and math.isfinite(lat)):
        raise CoordinateError("non-finite coordinate")
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise CoordinateError(f"out of range: lon={lon}, lat={lat}")
    if lon == 0 and lat == 0:
        raise CoordinateError("null island (0, 0)")
    return lon, lat


class NutsGazetteer:
    def __init__(self, rows: dict[str, tuple]):
        self.rows = rows

    @classmethod
    def from_csv(cls, path) -> "NutsGazetteer":
        p = Path(path)
        if not p.exists():
            return cls({})
        with p.open(encoding="utf-8", newline="") as fh:
            return cls({r["nuts_id"].strip().upper(): (r["lon"], r["lat"]) for r in csv.DictReader(fh)})


def nuts_codes(codes) -> list[str]:
    """Keep NUTS-2/3 style codes (must contain a digit); drops alpha-3 country codes and placeholders like 'anyw'."""
    return sorted({c.strip().upper() for c in codes if isinstance(c, str)
                   and NUTS_RE.match(c.strip().upper()) and any(ch.isdigit() for ch in c)})


def resolve_location(place_codes, gaz: NutsGazetteer) -> Location:
    raw = [c for c in place_codes if isinstance(c, str) and c.strip()]
    if not raw:
        return Location("unresolved", "no_place_of_performance")
    nuts = nuts_codes(raw)
    if not nuts:
        return Location("unresolved", "country_level_only")
    nuts3 = [c for c in nuts if len(c) == 5]
    if not nuts3:
        return Location("unresolved", "nuts_below_level3")
    if len(nuts3) > 1:
        return Location("unresolved", "ambiguous_multiple_nuts3")
    code = nuts3[0]
    if code not in gaz.rows:
        return Location("unresolved", "nuts3_not_in_gazetteer")
    try:
        lon, lat = validate_lonlat(*gaz.rows[code])
        x, y = _TO_25832.transform(lon, lat)
        if not (math.isfinite(x) and math.isfinite(y)):
            raise CoordinateError("transform produced non-finite values")
    except CoordinateError as exc:
        return Location("unresolved", f"invalid_coordinates: {exc}")
    warn = None if AREA_LON[0] <= lon <= AREA_LON[1] else "outside_epsg25832_area_of_use"
    return Location("resolved", None, lon, lat, x, y, "nuts3_representative_point", warn)
