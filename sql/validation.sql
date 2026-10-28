-- Duplicates (must return 0 rows)
SELECT source_system, source_record_id, count(*) FROM iris_staging.signal_ingest GROUP BY 1,2 HAVING count(*) > 1;
-- Wrong SRID or invalid geometry (must return 0 rows)
SELECT id FROM iris_staging.signal_ingest WHERE geom IS NOT NULL AND (ST_SRID(geom) <> 25832 OR NOT ST_IsValid(geom));
-- Geometry outside the expected European extent in EPSG:25832 (must return 0 rows)
SELECT id FROM iris_staging.signal_ingest WHERE geom IS NOT NULL AND NOT ST_Within(geom, ST_MakeEnvelope(-2500000, 3500000, 4500000, 10000000, 25832));
-- Records per signal type and geo status
SELECT unnest(signal_types) AS signal_type, geo_status, count(*) FROM iris_staging.signal_ingest GROUP BY 1,2 ORDER BY 1,2;
-- Missing fields
SELECT count(*) FILTER (WHERE title IS NULL) AS no_title, count(*) FILTER (WHERE published_at IS NULL) AS no_date, count(*) FILTER (WHERE source_url IS NULL) AS no_url FROM iris_staging.signal_ingest;
