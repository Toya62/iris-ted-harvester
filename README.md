# iris-ted-harvester (IRIS-SIG-50)

Harvests EU public procurement notices from the TED Search API v3 into `iris_staging.signal_ingest` (PostgreSQL 16 / PostGIS 3.4, point geometry in EPSG:25832).

## Assignment requirements (from the brief) and how each is met

| Requirement | Implementation |
|---|---|
| Objective: notices above EU thresholds for grid cabling, transformers, public DCs | `domain.py`: three categories queried separately, results merged per notice. TED notices are by definition EU-level procurement. |
| Confirm current source format | The brief names `https://ted.europa.eu/api/v2.0/notices/search`. That endpoint is obsolete (answers HTTP 202 without JSON). The client targets the current v3 endpoint `https://api.ted.europa.eu/v3/notices/search` and raises `TedFormatError` if a non-JSON/202 response is ever returned. |
| Preserve identifiers, titles, dates, URLs, geographic context | `publication-number`, `notice-title`, `publication-date`, HTML link, NUTS codes, city, CPV codes, buyer, plus the full raw payload (JSONB). |
| Idempotent load into PostgreSQL/PostGIS | `UNIQUE (source_system, source_record_id)` + upsert that updates only when `content_hash` changes. |
| EPSG:25832 points, document unresolved | NUTS-3 representative point transformed with pyproj. Unresolved cases keep a machine-readable reason. |
| Pagination, network failure, duplicates, malformed data, empty responses | Token (ITERATION) pagination; retry/backoff on network errors, 408/425/429/5xx, honours Retry-After; duplicate collapse; strict response checks; empty responses counted. |
| No credentials in code | Environment variables only (`.env.example`). |
| README, tests, sample output, validation queries, error/quality report | This file; `tests/`; `sql/002_validation_queries.sql`; JSON report printed and written on each run. |
| Invalid coordinates not silently accepted | `validate_lonlat` rejects non-numeric, NaN, out-of-range and (0,0); database CHECK constraints repeat the range and geom/status rules. |

## Domain filter
- grid_cabling: CPV 3132* and 45231400
- transformers: CPV 3117*
- public_data_centre: no CPV code exists, so full-text match on "data centre", "data center", "Rechenzentrum", "datacenter". Expect false positives; review with the domain owner.
- Country filter defaults to DEU via `place-of-performance-country-proc` (`TED_COUNTRIES`, or `--countries ALL`).

## Run
```
pip install -e ".[dev]"
python scripts/build_nuts_centroids.py          # needs `pip install shapely`; writes data/nuts3_centroids.csv
ted-harvester --dry-run --since 2026-10-01 --until 2026-10-27 --out out   # no database
export DATABASE_URL=postgresql://user:pass@host/db
ted-harvester --init-db                          # creates schema, then loads incrementally (DB watermark minus overlap)
pytest -q                                        # unit tests
TED_TEST_DSN=postgresql://... pytest -m integration
```
Without the centroid CSV every location is reported as unresolved (a warning is logged).

## Mapping assumptions
- Title: English preferred, then German, then any language; language stored in `title_lang`.
- Location: exactly one NUTS-3 code in `place-of-performance` resolves to the representative point of that region (precision is regional, not site-level). Country-level only, NUTS-2 only, several NUTS-3 codes, unknown codes and invalid gazetteer coordinates stay unresolved with `location_note`.
- Quality: `invalid` = missing title or invalid publication date (reported and stored in the reject table, not loaded); `warning` = missing CPV, unresolved location or out-of-area point; otherwise `ok`.
- Notices found by several categories are merged into one row with all categories.

## Status of verification (read this)
- Unit tests were run in a development sandbox: 38 passed before two test assertions about the report's `load` counters were corrected in this commit (code unchanged). The corrected tests, the CI run on GitHub, the live API call, `build_nuts_centroids.py` and the PostgreSQL path have NOT been re-run on this exact commit. Check the CI result first.
- An earlier version of this project, run against the live TED API for 2026-10-01 to 2026-10-27 (DEU), fetched 127 raw notices; 40 were processed, of which 36 got a location and 4 stayed unresolved. That earlier code is not what is in this repo, so no sample output file is included. Generate one with the dry-run command above.
- The PostgreSQL upsert (`xmax = 0` insert detection) is untested against a real database.

## Known limitations
- Regional precision only; no address geocoding.
- Data-centre detection is text-based.
- `--limit` is applied after fetching.
- TED ITERATION mode is documented for up to roughly 15,000 hits per query; narrow `TED_WINDOW_DAYS` if a window approaches that.
