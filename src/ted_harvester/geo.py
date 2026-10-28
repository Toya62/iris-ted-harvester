"""Geospatial utilities for resolving NUTS regions to EPSG:25832 coordinates."""

import csv
import logging
import math
from typing import Dict, Iterable, Optional, Tuple

from pyproj import Transformer

logger = logging.getLogger(__name__)

# Coordinate transformer: WGS84 (EPSG:4326) to ETRS89 / UTM zone 32N (EPSG:25832)
COORDINATE_TRANSFORMER = Transformer.from_crs(4326, 25832, always_xy=True)

# Broad geographic bounding box for Europe (WGS84 degrees)
EUROPE_LON_BOUNDS = (-35.0, 45.0)
EUROPE_LAT_BOUNDS = (30.0, 75.0)


def load_centroids(file_path: str) -> Dict[str, Tuple[float, float]]:
    """
    Load NUTS-3 centroid lookup table from CSV.
    Expected headers: nuts_id, lon, lat
    """
    centroids: Dict[str, Tuple[float, float]] = {}
    with open(file_path, mode="r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            nuts_id = row["nuts_id"].strip()
            try:
                lon = float(row["lon"])
                lat = float(row["lat"])
                centroids[nuts_id] = (lon, lat)
            except (ValueError, KeyError) as exc:
                logger.debug("Skipping invalid centroid row for %s: %s", nuts_id, exc)
    return centroids


def to_25832(lon: float, lat: float) -> Tuple[float, float]:
    """
    Validate WGS84 longitude/latitude and project to EPSG:25832 (meters).
    Raises ValueError on non-finite, out-of-bounds, or unprojectable coordinates.
    """
    if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
        raise ValueError(f"Coordinates must be numeric, got lon={type(lon).__name__}, lat={type(lat).__name__}")

    if not (math.isfinite(lon) and math.isfinite(lat)):
        raise ValueError(f"Coordinates must be finite, got lon={lon}, lat={lat}")

    if not (EUROPE_LON_BOUNDS[0] <= lon <= EUROPE_LON_BOUNDS[1] and EUROPE_LAT_BOUNDS[0] <= lat <= EUROPE_LAT_BOUNDS[1]):
        raise ValueError(f"Coordinates ({lon}, {lat}) fall outside expected European bounds")

    x, y = COORDINATE_TRANSFORMER.transform(lon, lat)

    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValueError(f"Projection to EPSG:25832 failed for lon={lon}, lat={lat}")

    return round(x, 2), round(y, 2)


def resolve(
    nuts_codes: Iterable[str],
    centroids: Dict[str, Tuple[float, float]],
) -> Tuple[Optional[float], Optional[float], str, str]:
    """
    Resolve notice places of performance to a representative point geometry.

    Rules:
      - Exactly one NUTS-3 region (5-character code) -> 'resolved' with EPSG:25832 (x, y).
      - Multiple distinct NUTS-3 regions -> 'ambiguous' (no point assigned).
      - Country-only or coarse NUTS (1/2) -> 'unresolved' (no point assigned).
      - Missing or unprojectable centroid -> 'unresolved'.

    Returns:
      (x, y, geo_status, geo_note)
    """
    nuts3_codes = sorted({code for code in nuts_codes if isinstance(code, str) and len(code.strip()) == 5})

    if not nuts3_codes:
        return None, None, "unresolved", "country or coarse level only"

    if len(nuts3_codes) > 1:
        joined_codes = ",".join(nuts3_codes)
        return None, None, "ambiguous", f"multiple NUTS-3 regions: {joined_codes}"

    target_nuts = nuts3_codes[0]
    centroid = centroids.get(target_nuts)

    if centroid is None:
        return None, None, "unresolved", f"no centroid for {target_nuts}"

    try:
        x, y = to_25832(centroid[0], centroid[1])
        return x, y, "resolved", f"NUTS-3 region centroid {target_nuts}"
    except ValueError as exc:
        return None, None, "unresolved", f"invalid coordinate: {exc}"
