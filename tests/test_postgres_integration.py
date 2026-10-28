"""Opt-in integration test: TED_TEST_DSN=postgresql://... pytest -m integration (needs PostgreSQL 16 + PostGIS 3.4)."""
import os
from pathlib import Path
import pytest

from ted_harvester.load import upsert
from ted_harvester.normalize import normalize

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("TED_TEST_DSN"), reason="TED_TEST_DSN not set"),
]


def test_upsert_idempotent_and_srid():
    import psycopg

    dsn = os.environ["TED_TEST_DSN"]
    schema_sql = (Path(__file__).resolve().parents[1] / "sql" / "schema.sql").read_text(encoding="utf-8")
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
            cur.execute("DELETE FROM iris_staging.signal_ingest WHERE source_record_id = 'it-1-2026'")
        conn.commit()

        notice = {
            "publication-number": "it-1-2026",
            "notice-title": {"eng": "Integration test cable notice"},
            "publication-date": "2026-10-01+02:00",
            "place-of-performance": ["DEA18"],
            "buyer-country": ["DEU"],
        }
        centroids = {"DEA18": (7.19, 51.18)}
        rec, _ = normalize(notice, "grid_cabling", centroids)
        a = upsert(conn, [rec])
        b = upsert(conn, [rec])
        assert (a["inserted"], b["inserted"], b["unchanged"]) == (1, 0, 1)

        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*), max(ST_SRID(geom)) FROM iris_staging.signal_ingest WHERE source_record_id = 'it-1-2026'"
            )
            assert cur.fetchone() == (1, 25832)
