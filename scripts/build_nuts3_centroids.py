"""Download Eurostat GISCO NUTS label points and write data/nuts3_centroids.csv (NUTS-3 only)."""
import csv
import os

import requests

URL = "https://gisco-services.ec.europa.eu/distribution/v2/nuts/geojson/NUTS_LB_2021_4326.geojson"


def main(out="data/nuts3_centroids.csv"):
    r = requests.get(URL, timeout=60)
    r.raise_for_status()
    rows = []
    for f in r.json()["features"]:
        nid = f["properties"]["NUTS_ID"]
        if len(nid) == 5:
            lon, lat = f["geometry"]["coordinates"][:2]
            rows.append((nid, lon, lat))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["nuts_id", "lon", "lat"])
        w.writerows(rows)
    print(f"written {len(rows)}")


if __name__ == "__main__":
    main()
