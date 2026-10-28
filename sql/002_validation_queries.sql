-- 1. No duplicates (expect 0 rows)
SELECT source_system, source_record_id, count(*) FROM iris_staging.signal_ingest GROUP BY 1,2 HAVING count(*) > 1;
-- 2. All geometries are EPSG:25832 points and inside plausible bounds (expect 0 rows)
SELECT source_record_id FROM iris_staging.signal_ingest
WHERE geom IS NOT NULL AND (ST_SRID(geom) <> 25832 OR NOT ST_Within(geom, ST_MakeEnvelope(100000, 4500000, 1000000, 6500000, 25832)));
-- 3. Geometry round-trips to the stored WGS84 coordinates (expect 0 rows, tolerance ~5 m)
SELECT source_record_id FROM iris_staging.signal_ingest
WHERE geom IS NOT NULL AND ST_Distance(ST_Transform(geom, 4326)::geography, ST_SetSRID(ST_MakePoint(lon_4326, lat_4326), 4326)::geography) > 5;
-- 4. Unresolved locations and why
SELECT location_note, count(*) FROM iris_staging.signal_ingest WHERE location_status = 'unresolved' GROUP BY 1 ORDER BY 2 DESC;
-- 5. Quality overview and category counts
SELECT quality_status, count(*) FROM iris_staging.signal_ingest GROUP BY 1;
SELECT unnest(signal_categories) AS category, count(*) FROM iris_staging.signal_ingest GROUP BY 1;
-- 6. Rejected raw records
SELECT reason, count(*) FROM iris_staging.signal_ingest_reject GROUP BY 1;
