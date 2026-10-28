CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS iris_staging;

CREATE TABLE IF NOT EXISTS iris_staging.signal_ingest (
    id               bigserial PRIMARY KEY,
    source_system    text        NOT NULL,
    source_record_id text        NOT NULL,
    signal_types     text[]      NOT NULL,
    title            text,
    published_at     date,
    source_url       text,
    country_code     text,
    nuts_codes       text[]      NOT NULL DEFAULT '{}',
    geom             geometry(Point, 25832),
    geo_status       text        NOT NULL,
    geo_note         text,
    raw              jsonb       NOT NULL,
    content_hash     text        NOT NULL,
    ingested_at      timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT signal_ingest_uq UNIQUE (source_system, source_record_id),
    CONSTRAINT geo_status_chk CHECK (geo_status IN ('resolved','ambiguous','unresolved')),
    CONSTRAINT geom_status_chk CHECK ((geom IS NOT NULL) = (geo_status = 'resolved'))
);

CREATE INDEX IF NOT EXISTS signal_ingest_geom_gix ON iris_staging.signal_ingest USING gist (geom);
CREATE INDEX IF NOT EXISTS signal_ingest_pub_ix ON iris_staging.signal_ingest (published_at);
