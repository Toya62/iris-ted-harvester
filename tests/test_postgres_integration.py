"""Opt-in: TED_TEST_DSN=postgresql://... pytest -m integration (needs PostGIS 3.4)."""
import os
import pytest
from conftest import notice
from ted_harvester.normalize import normalize

pytestmark = [pytest.mark.integration, pytest.mark.skipif(not os.environ.get("TED_TEST_DSN"), reason="TED_TEST_DSN not set")]


def test_upsert_idempotent_and_srid(gaz):
    from ted_harvester.store import PostgresStore
    st = PostgresStore(os.environ["TED_TEST_DSN"])
    st.ensure_schema()
    with st.conn.cursor() as cur:
        cur.execute("DELETE FROM iris_staging.signal_ingest WHERE source_record_id = 'it-1-2026'")
    st.conn.commit()
    r = normalize(notice("it-1-2026"), ["grid_cabling"], gaz)
    a, b = st.upsert([r]), st.upsert([r])
    assert (a["inserted"], b["inserted"], b["unchanged"]) == (1, 0, 1)
    with st.conn.cursor() as cur:
        cur.execute("SELECT count(*), max(ST_SRID(geom)) FROM iris_staging.signal_ingest WHERE source_record_id = 'it-1-2026'")
        assert cur.fetchone() == (1, 25832)
