# IRIS-SIG-50: TED infrastructure notices to PostGIS

Harvests EU public procurement notices (grid cabling, transformers, public data centres) from Tenders Electronic Daily and loads them idempotently into `iris_staging.signal_ingest` (PostgreSQL 16 / PostGIS 3.4, EPSG:25832). The original brief is in `docs/ASSIGNMENT.md`.

## Data source
- The brief names `https://ted.europa.eu/api/v2.0/notices/search`. That endpoint is obsolete: in my earlier check it returned HTTP 202 with an empty HTML body. The harvester rejects any non-JSON/202 response instead of treating it as empty.
- Alternative used: the public TED Search API v3, `POST https://api.ted.europa.eu/v3/notices/search` (anonymous search, token pagination). Verify access and field names against the current TED API documentation before production use.

## Filters
| Signal type | Query |
|---|---|
| grid_cabling | CPV 3132* or 45231400 |
| transformers | CPV 3117* |
| public_data_centre | full-text: data centre / data center / Rechenzentrum (no dedicated CPV code) |

## Mapping and geocoding
- publication-number is the source id; title prefers English; URL from links, else the TED detail page.
- Place of performance gives NUTS codes. A point is created only when exactly one NUTS-3 region is listed (Eurostat GISCO label point, projected to EPSG:25832). Country-level, coarse or multi-region notices get no geometry; the reason is stored in `geo_note`.
- Coordinates are validated (finite, Europe extent); invalid ones are never stored.
- Upsert on `(source_system, source_record_id)`; rows change only if `content_hash` changes.

## Run
```
pip install -e .[dev]
python scripts/build_nuts3_centroids.py        # downloads centroid data
psql -f sql/schema.sql
cp .env.example .env                           # set TED_DSN
ted-harvest --since 2026-10-01 --dry-run       # no database
ted-harvest --since 2026-10-01                 # load
psql -f sql/validation.sql
pytest
```
The CLI prints a JSON quality report (counts, geo status, field issues, per-category errors) and writes `output/sample.json`.

## Status and limitations
- Tests use mocks/fixtures only. This branch has not yet been run end to end: tests, the live TED v3 query syntax and field names, and the SQL against a real PostGIS are unverified.
- Locations are region-level, not site-level.
- The CPV filter can return loosely related works notices; the data-centre text query may be noisy.
- Only the first notice-language title is kept when no English one exists.
