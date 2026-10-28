# IRIS-SIG-50: EU Tenders Electronic Daily (TED) Infrastructure API Harvester

Harvests EU public procurement notices for grid cabling, transformers, and public data centres from Tenders Electronic Daily (TED) and loads them idempotently into `iris_staging.signal_ingest` (PostgreSQL 16 / PostGIS 3.4, EPSG:25832).

---

## 1. Data Source & Endpoint

- **Brief endpoint (`https://ted.europa.eu/api/v2.0/notices/search`)**:
  Obsolete. Testing this endpoint returns `HTTP 404 / 202` HTML responses rather than JSON API payloads. The harvester client strictly validates responses (`Content-Type: application/json` and structured payload check) and explicitly rejects non-JSON/202 responses with `TedError`.
- **Justified Alternative**:
  The official public TED Search API v3: `POST https://api.ted.europa.eu/v3/notices/search`.
  - Supports anonymous token pagination (`paginationMode: ITERATION` with `iterationNextToken`).
  - Supports expert queries (`q`) with CPV prefixes, full-text boolean operators, and date ranges.
  - Verified live and operational with active EU procurement data.
- **EU Thresholds**:
  By EU public procurement directives (Directive 2014/24/EU, Directive 2014/25/EU), TED publishes only notices above EU procurement thresholds. All notices harvested through TED meet this threshold criterion by definition.

---

## 2. Filters & Signal Types

| Signal Type | Query Filter | Notes |
|---|---|---|
| `grid_cabling` | `(classification-cpv=3132* OR classification-cpv=45231400)` | Power distribution cables & laying of electricity power lines |
| `transformers` | `classification-cpv=3117*` | Power & distribution transformers |
| `public_data_centre` | `FT~("data centre" OR "data center" OR "Rechenzentrum")` | Full-text search (no single CPV code exists for data centres) |

Queries are bounded by `publication-date>=YYYYMMDD` (and optionally `<=YYYYMMDD`).

---

## 3. Geocoding & Mapping Assumptions

- **Identifier**: `publication-number` is preserved as `source_record_id`, with `source_system = 'ted'`.
- **Title**: Prefers English (`eng`/`ENG`), falls back to German (`deu`/`DEU`), then first available language.
- **Source URL**: Extracted from `links.htmlDirect` or `links.html` (ENG/DEU), falling back to canonical `https://ted.europa.eu/en/notice/-/detail/<pid>`.
- **Geographic Resolution (EPSG:25832)**:
  - Source places of performance are parsed from `place-of-performance` NUTS codes.
  - **Single NUTS-3 region**: Centroid resolved via Eurostat GISCO NUTS-3 label points (`data/nuts3_centroids.csv`) and transformed to `EPSG:25832` (ETRS89 / UTM zone 32N) with `geo_status = 'resolved'`.
  - **Multiple NUTS-3 regions**: Geometry set to `NULL`, with `geo_status = 'ambiguous'` and `geo_note = 'multiple NUTS-3 regions: <codes>'`.
  - **Country or coarse (NUTS-1/2) only**: Geometry set to `NULL`, with `geo_status = 'unresolved'` and `geo_note = 'country or coarse level only'`.
  - **Coordinate Validation**: Non-numeric, infinite/NaN, or out-of-European-extent coordinates are strictly rejected (`geo_status = 'unresolved'` with validation error).
- **Idempotency & Deduplication**:
  - Notices matching multiple signal categories are merged by `(source_system, source_record_id)` with unioned `signal_types`.
  - Deterministic SHA-256 `content_hash` computed over core fields.
  - Database upsert uses PostgreSQL `ON CONFLICT (source_system, source_record_id) DO UPDATE ... WHERE iris_staging.signal_ingest.content_hash IS DISTINCT FROM EXCLUDED.content_hash`. Re-runs on unchanged data result in zero updates (`unchanged`).

---

## 4. Setup & Running

### Requirements
- Python 3.10+
- PostgreSQL 16 + PostGIS 3.4 (optional for `--dry-run` and mocks; required for database ingestion)

### Install Dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Download NUTS-3 Centroids
Fetches open-access Eurostat GISCO label points:
```bash
python scripts/build_nuts3_centroids.py
```

### Database Initialization (PostgreSQL / PostGIS)
```bash
psql "$TED_DSN" -f sql/schema.sql
```

### Run Harvester
```bash
# Dry-run (no DB needed; writes output/sample.json & output/quality_report.json)
ted-harvest --since 2026-10-01 --until 2026-10-20 --dry-run

# Production ingestion into PostGIS
export TED_DSN="postgresql://user:password@localhost:5432/iris"
ted-harvest --since 2026-10-01
```

### Validate Ingestion
```bash
psql "$TED_DSN" -f sql/validation.sql
```

### Run Automated Tests
```bash
# Unit tests with mocks/fixtures (includes retry, malformed data, deduplication, idempotency)
pytest -v

# Opt-in PostGIS live integration test (when DB is available)
TED_TEST_DSN="postgresql://user:password@localhost:5432/iris" pytest -m integration
```

---

## 5. Sample Output & Quality Report

Running `ted-harvest` writes:
- `output/sample.json`: Anonymized public-source records with resolved coordinates, `geo_status`, `nuts_codes`, and `content_hash`.
- `output/quality_report.json`: Execution quality summary including notice counts, category breakdowns, geographic resolution statuses, field issues, and database load statistics.

Sample Quality Report snippet:
```json
{
  "raw_notices": 21,
  "unique_records": 21,
  "by_signal_type": {
    "grid_cabling": 10,
    "transformers": 10,
    "public_data_centre": 1
  },
  "geo": {
    "resolved": 17,
    "ambiguous: multiple NUTS-3 regions: EE001,EE004,EE008,EE009,EE00A": 1,
    "unresolved: country or coarse level only": 2,
    "ambiguous: multiple NUTS-3 regions: IE061,IEZZZ": 1
  },
  "field_issues": {},
  "category_errors": {},
  "load": null
}
```

---

## 6. Known Limitations

1. **Resolution Granularity**: Geometries represent NUTS-3 regional centroids, not exact building / site addresses.
2. **Data Centre CPV Absence**: Public data centre procurements are discovered via full-text search (`FT~`), which may yield occasional peripheral IT tenders.
3. **Multi-Region Notices**: Procurement lots covering multiple NUTS-3 regions or entire nations are left without point geometry (`ambiguous` / `unresolved`) to prevent misleading coordinate assignments.
