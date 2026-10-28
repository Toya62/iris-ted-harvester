"""Build data/nuts3_centroids.csv from Eurostat GISCO NUTS-3 polygons (EPSG:4326).
Uses shapely's representative_point() so the point always lies INSIDE the region (a plain centroid may not).
Requires: pip install shapely. Source: https://gisco-services.ec.europa.eu (Eurostat, open data)."""
import csv
import json
import sys
import urllib.request
from pathlib import Path

from shapely.geometry import shape

URL = "https://gisco-services.ec.europa.eu/distribution/v2/nuts/geojson/NUTS_RG_01M_2021_4326_LEVL_3.geojson"
out = Path(sys.argv[1] if len(sys.argv) > 1 else "data/nuts3_centroids.csv")
out.parent.mkdir(parents=True, exist_ok=True)
data = json.load(urllib.request.urlopen(URL, timeout=120))
with out.open("w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["nuts_id", "lon", "lat", "name"])
    for f in data["features"]:
        p = shape(f["geometry"]).representative_point()
        w.writerow([f["properties"]["NUTS_ID"], round(p.x, 6), round(p.y, 6), f["properties"].get("NAME_LATN", "")])
print("wrote", out)
