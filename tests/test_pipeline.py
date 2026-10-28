from datetime import date
from conftest import make_client, notice, page, resp
from ted_harvester.pipeline import run, windows
from ted_harvester.store import MemoryStore

D1, D2 = date(2026, 10, 1), date(2026, 10, 10)
EMPTY = lambda: resp(page([]))


def responses(cat1, cat2=None, cat3=None):
    return [resp(cat1), resp(cat2 or page([])), resp(cat3 or page([]))]


def go(settings, gaz, store, resps):
    c, _ = make_client(settings, resps)
    return run(settings, c, store, gaz, D1, D2)


def base_pages():
    bad = {"notice-title": {"eng": "no id"}}
    return responses(page([notice("1-2026"), notice("2-2026", nuts=("DEA11", "DEA22")), bad, notice("3-2026", title={}, date="x")]),
                     page([notice("1-2026")]))


def test_dedupe_rejects_and_report(settings, gaz):
    store = MemoryStore()
    recs, rep = go(settings, gaz, store, base_pages())
    assert sorted(r["source_record_id"] for r in recs) == ["1-2026", "2-2026"]
    assert rep["duplicates_collapsed"] == 1 and rep["rejected"]["missing_publication_number"] == 1
    assert rep["quality"] == {"ok": 1, "warning": 1, "invalid": 1} and rep["load"]["inserted"] == 2
    assert rep["issues"]["location_unresolved:ambiguous_multiple_nuts3"] == 1
    assert next(r for r in recs if r["source_record_id"] == "1-2026")["signal_categories"] == ["grid_cabling", "transformers"]
    assert len(store.rejects) == 2


def test_rerun_is_idempotent(settings, gaz):
    store = MemoryStore()
    go(settings, gaz, store, base_pages())
    snap = {k: v["content_hash"] for k, v in store.rows.items()}
    _, rep = go(settings, gaz, store, base_pages())
    assert rep["load"]["unchanged"] == 2 and rep["load"]["inserted"] == 0 and rep["load"]["updated"] == 0
    assert {k: v["content_hash"] for k, v in store.rows.items()} == snap


def test_changed_notice_updates_not_duplicates(settings, gaz):
    store = MemoryStore()
    go(settings, gaz, store, base_pages())
    changed = notice("1-2026", title={"eng": "Corrected"})
    _, rep = go(settings, gaz, store, responses(page([changed])))
    assert rep["load"]["updated"] == 1 and len(store.rows) == 2 and store.rows[("TED", "1-2026")]["title"] == "Corrected"


def test_all_empty(settings, gaz):
    recs, rep = go(settings, gaz, MemoryStore(), [EMPTY(), EMPTY(), EMPTY()])
    assert recs == [] and rep["empty_windows"] == 1 and rep["load"]["inserted"] == 0


def test_failing_category_reported_others_load(settings, gaz):
    store = MemoryStore()
    fail = [resp({}, 500)] * (settings.max_retries + 1)
    recs, rep = go(settings, gaz, store, fail + [resp(page([notice("5-2026")])), EMPTY()])
    assert len(rep["category_errors"]) == 1 and [r["source_record_id"] for r in recs] == ["5-2026"]


def test_windows():
    ws = list(windows(date(2026, 1, 1), date(2026, 3, 1), 30))
    assert ws == [(date(2026, 1, 1), date(2026, 1, 30)), (date(2026, 1, 31), date(2026, 3, 1))]
