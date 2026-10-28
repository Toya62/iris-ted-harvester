"""Download Eurostat GISCO NUTS label points and generate data/nuts3_centroids.csv."""

import argparse
import csv
import logging
import os
import sys

import requests

logger = logging.getLogger("build_nuts3_centroids")

EUROSTAT_GISCO_URL = (
    "https://gisco-services.ec.europa.eu/distribution/v2/nuts/geojson/NUTS_LB_2021_4326.geojson"
)


def download_and_extract_centroids(output_path: str = "data/nuts3_centroids.csv") -> int:
    """
    Download official Eurostat GISCO 2021 label points GeoJSON and filter for NUTS-3 (5-char codes).
    Writes output CSV with columns: nuts_id, lon, lat
    """
    logger.info("Downloading Eurostat GISCO NUTS label points from %s...", EUROSTAT_GISCO_URL)
    response = requests.get(EUROSTAT_GISCO_URL, timeout=60)
    response.raise_for_status()

    geojson_data = response.json()
    features = geojson_data.get("features", [])
    logger.info("Retrieved %d features from Eurostat. Filtering NUTS-3 regions...", len(features))

    centroid_rows = []
    for feature in features:
        properties = feature.get("properties", {})
        nuts_id = properties.get("NUTS_ID", "").strip()

        # NUTS-3 identifiers in EU classification have exactly 5 characters (e.g. DEA18)
        if len(nuts_id) == 5:
            coordinates = feature.get("geometry", {}).get("coordinates", [])
            if len(coordinates) >= 2:
                lon, lat = coordinates[0], coordinates[1]
                centroid_rows.append((nuts_id, lon, lat))

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, mode="w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["nuts_id", "lon", "lat"])
        writer.writerows(centroid_rows)

    logger.info("Saved %d NUTS-3 region centroids to %s", len(centroid_rows), output_path)
    return len(centroid_rows)


def main():
    parser = argparse.ArgumentParser(description="Download NUTS-3 centroid coordinates.")
    parser.add_argument(
        "--output",
        default="data/nuts3_centroids.csv",
        help="Target output CSV path (default: data/nuts3_centroids.csv)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    try:
        count = download_and_extract_centroids(args.output)
        print(f"Successfully generated {args.output} with {count} centroids.")
    except Exception as exc:
        logger.error("Failed to build centroids: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
