"""Idempotent loading: unique on (source_system, source_record_id); rows are only updated if content_hash changed."""
from __future__ import annotations

from pathlib import Path

from psycopg.types.json import Jsonb

COLS = ["source_system", "source_record_id", "signal_type", "signal_categories", "title", "title_lang",
        "publication_date", "source_url", "notice_type", "buyer_name", "country_code", "nuts_codes", "place_text",
        "cpv_codes", "estimated_value", "location_status", "location_note", "lon_4326", "lat_4326",
        "quality_status", "quality_issues", "content_hash", "raw_payload"]
GEOM = ("CASE WHEN %(x_25832)s::float8 IS NULL THEN NULL "
        "ELSE ST_SetSRID(ST_MakePoint(%(x_25832)s::float8, %(y_25832)s::float8), 25832) END")
UPSERT_SQL = (
    "INSERT INTO iris_staging.signal_ingest ({cols}, geom) VALUES ({vals}, {geom}) "
    "ON CONFLICT (source_system, source_record_id) DO UPDATE SET {sets}, geom = EXCLUDED.geom, updated_at = now() "
    "WHERE iris_staging.signal_ingest.content_hash IS DISTINCT FROM EXCLUDED.content_hash "
    "RETURNING (xmax = 0) AS inserted"
).format(cols=", ".join(COLS), vals=", ".join(f"%({c})s" for c in COLS), geom=GEOM,
         sets=", ".join(f"{c} = EXCLUDED.{c}" for c in COLS if c not in ("source_system", "source_record_id")))


class MemoryStore:
    """Same semantics as PostgresStore, for --dry-run and tests."""

    def __init__(self):
        self.rows: dict[tuple, dict] = {}
        self.rejects: list[tuple] = []

    def watermark(self):
        d = [r["publication_date"] for r in self.rows.values() if r["publication_date"]]
        return max(d) if d else None

    def upsert(self, records) -> dict:
        st = {"inserted": 0, "updated": 0, "unchanged": 0}
        for r in records:
            key = (r["source_system"], r["source_record_id"])
            old = self.rows.get(key)
            if old is None:
                st["inserted"] += 1
            elif old["content_hash"] != r["content_hash"]:
                st["updated"] += 1
            else:
                st["unchanged"] += 1
                continue
            self.rows[key] = r
        return st

    def reject(self, reason, raw):
        self.rejects.append((reason, raw))


class PostgresStore:
    def __init__(self, dsn: str):
        import psycopg
        self.conn = psycopg.connect(dsn)

    def ensure_schema(self):
        sql = (Path(__file__).resolve().parents[2] / "sql" / "001_signal_ingest.sql").read_text(encoding="utf-8")
        with self.conn.cursor() as cur:
            cur.execute(sql)
        self.conn.commit()

    def watermark(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT max(publication_date) FROM iris_staging.signal_ingest WHERE source_system = 'TED'")
            return cur.fetchone()[0]

    def upsert(self, records) -> dict:
        st = {"inserted": 0, "updated": 0, "unchanged": 0}
        try:
            with self.conn.cursor() as cur:
                for r in records:
                    p = dict(r)
                    p["quality_issues"], p["raw_payload"] = Jsonb(r["quality_issues"]), Jsonb(r["raw_payload"], dumps=_dumps)
                    cur.execute(UPSERT_SQL, p)
                    row = cur.fetchone()
                    st["unchanged" if row is None else ("inserted" if row[0] else "updated")] += 1
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return st

    def reject(self, reason, raw):
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO iris_staging.signal_ingest_reject (source_system, reason, raw_payload) "
                        "VALUES ('TED', %s, %s)", (reason, Jsonb(raw, dumps=_dumps)))
        self.conn.commit()


def _dumps(o):
    import json
    return json.dumps(o, default=str)
