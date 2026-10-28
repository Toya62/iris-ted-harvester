import json

UPSERT = """
INSERT INTO iris_staging.signal_ingest
 (source_system, source_record_id, signal_types, title, published_at, source_url, country_code,
  nuts_codes, geom, geo_status, geo_note, raw, content_hash)
VALUES (%(source_system)s, %(source_record_id)s, %(signal_types)s, %(title)s, %(published_at)s,
  %(source_url)s, %(country_code)s, %(nuts_codes)s,
  CASE WHEN %(x)s::float8 IS NULL THEN NULL ELSE ST_SetSRID(ST_MakePoint(%(x)s::float8, %(y)s::float8), 25832) END,
  %(geo_status)s, %(geo_note)s, %(raw)s::jsonb, %(content_hash)s)
ON CONFLICT (source_system, source_record_id) DO UPDATE SET
  signal_types = EXCLUDED.signal_types, title = EXCLUDED.title, published_at = EXCLUDED.published_at,
  source_url = EXCLUDED.source_url, country_code = EXCLUDED.country_code, nuts_codes = EXCLUDED.nuts_codes,
  geom = EXCLUDED.geom, geo_status = EXCLUDED.geo_status, geo_note = EXCLUDED.geo_note,
  raw = EXCLUDED.raw, content_hash = EXCLUDED.content_hash, updated_at = now()
WHERE iris_staging.signal_ingest.content_hash IS DISTINCT FROM EXCLUDED.content_hash
RETURNING (xmax = 0) AS inserted
"""


def upsert(conn, records):
    """Idempotent load. Returns counts of inserted / updated / unchanged records."""
    ins = upd = 0
    with conn.cursor() as cur:
        for r in records:
            params = dict(r, raw=json.dumps(r["raw"]))
            cur.execute(UPSERT, params)
            row = cur.fetchone()
            if row is not None:
                ins, upd = (ins + 1, upd) if row[0] else (ins, upd + 1)
    conn.commit()
    return {"inserted": ins, "updated": upd, "unchanged": len(records) - ins - upd}
