CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS iris_staging;

CREATE TABLE IF NOT EXISTS iris_staging.signal_ingest (
    id                 BIGSERIAL PRIMARY KEY,
    source_system      TEXT        NOT NULL,
    source_record_id   TEXT        NOT NULL,
    signal_type        TEXT        NOT NULL,
    signal_categories  TEXT[]      NOT NULL,
    title              TEXT,
    title_lang         TEXT,
    publication_date   DATE,
    source_url         TEXT,
    notice_type        TEXT,
    buyer_name         TEXT,
    country_code       TEXT,
    nuts_codes         TEXT[]      NOT NULL DEFAULT '{}',
    place_text         TEXT,
    cpv_codes          TEXT[]      NOT NULL DEFAULT '{}',
    estimated_value    NUMERIC,
    location_status    TEXT        NOT NULL CHECK (location_status IN ('resolved','unresolved')),
    location_note      TEXT,
    lon_4326           DOUBLE PRECISION,
    lat_4326           DOUBLE PRECISION,
    geom               geometry(Point, 25832),
    quality_status     TEXT        NOT NULL CHECK (quality_status IN ('ok','warning','invalid')),
    quality_issues     JSONB       NOT NULL DEFAULT '[]'::jsonb,
    content_hash       TEXT        NOT NULL,
    raw_payload        JSONB       NOT NULL,
    first_seen_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ux_signal_ingest_source UNIQUE (source_system, source_record_id),
    CONSTRAINT ck_geom_matches_status CHECK ((location_status = 'resolved') = (geom IS NOT NULL)),
    CONSTRAINT ck_lonlat_range CHECK (
        (lon_4326 IS NULL AND lat_4326 IS NULL)
        OR (lon_4326 BETWEEN -180 AND 180 AND lat_4326 BETWEEN -90 AND 90))
);
CREATE INDEX IF NOT EXISTS ix_signal_ingest_geom ON iris_staging.signal_ingest USING gist (geom);
CREATE INDEX IF NOT EXISTS ix_signal_ingest_pubdate ON iris_staging.signal_ingest (source_system, publication_date);

CREATE TABLE IF NOT EXISTS iris_staging.signal_ingest_reject (
    id            BIGSERIAL PRIMARY KEY,
    source_system TEXT        NOT NULL,
    reason        TEXT        NOT NULL,
    raw_payload   JSONB,
    rejected_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
