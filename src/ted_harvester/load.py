"""Database loading logic for idempotent persistence into iris_staging.signal_ingest."""

import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

UPSERT_SQL = """
INSERT INTO iris_staging.signal_ingest (
    source_system,
    source_record_id,
    signal_types,
    title,
    published_at,
    source_url,
    country_code,
    nuts_codes,
    geom,
    geo_status,
    geo_note,
    raw,
    content_hash
) VALUES (
    %(source_system)s,
    %(source_record_id)s,
    %(signal_types)s,
    %(title)s,
    %(published_at)s,
    %(source_url)s,
    %(country_code)s,
    %(nuts_codes)s,
    CASE
        WHEN %(x)s::float8 IS NULL THEN NULL
        ELSE ST_SetSRID(ST_MakePoint(%(x)s::float8, %(y)s::float8), 25832)
    END,
    %(geo_status)s,
    %(geo_note)s,
    %(raw)s::jsonb,
    %(content_hash)s
)
ON CONFLICT (source_system, source_record_id) DO UPDATE SET
    signal_types = EXCLUDED.signal_types,
    title = EXCLUDED.title,
    published_at = EXCLUDED.published_at,
    source_url = EXCLUDED.source_url,
    country_code = EXCLUDED.country_code,
    nuts_codes = EXCLUDED.nuts_codes,
    geom = EXCLUDED.geom,
    geo_status = EXCLUDED.geo_status,
    geo_note = EXCLUDED.geo_note,
    raw = EXCLUDED.raw,
    content_hash = EXCLUDED.content_hash,
    updated_at = now()
WHERE iris_staging.signal_ingest.content_hash IS DISTINCT FROM EXCLUDED.content_hash
RETURNING (xmax = 0) AS is_new_insert;
"""


def upsert(conn: Any, records: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Idempotently upsert normalized signal records into PostgreSQL / PostGIS.

    Uses PostgreSQL's system column xmax to distinguish inserts from updates:
      - xmax = 0 indicates a newly inserted row.
      - xmax != 0 indicates an existing row updated because content_hash changed.
      - No row returned indicates the record was unchanged (WHERE filter skipped update).

    Returns a dictionary of execution counts:
      {"inserted": int, "updated": int, "unchanged": int}
    """
    inserted_count = 0
    updated_count = 0

    with conn.cursor() as cursor:
        for record in records:
            params = dict(record)
            params["raw"] = json.dumps(record.get("raw", {}), default=str)

            cursor.execute(UPSERT_SQL, params)
            result = cursor.fetchone()

            if result is not None:
                is_insert = result[0]
                if is_insert:
                    inserted_count += 1
                else:
                    updated_count += 1

    conn.commit()

    unchanged_count = len(records) - inserted_count - updated_count
    logger.info(
        "Staging load completed: %d inserted, %d updated, %d unchanged (total %d)",
        inserted_count,
        updated_count,
        unchanged_count,
        len(records),
    )

    return {
        "inserted": inserted_count,
        "updated": updated_count,
        "unchanged": unchanged_count,
    }
