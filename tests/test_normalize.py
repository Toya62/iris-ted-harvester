import pytest
from conftest import notice
from ted_harvester.normalize import RejectedRecord, normalize


def test_full_mapping(gaz):
    n = notice()
    r = normalize(n, ["grid_cabling"], gaz)
    assert r["source_record_id"] == "100001-2026" and r["source_system"] == "TED"
    assert r["title_lang"] == "eng" and r["publication_date"].isoformat() == "2026-10-01"
    assert r["source_url"].endswith("/100001-2026") and r["cpv_codes"] == ["31321300"] and r["nuts_codes"] == ["DEA13"]
    assert r["buyer_name"] == "Stadtwerke" and r["estimated_value"] == 1000.5 and r["country_code"] == "DEU"
    assert r["location_status"] == "resolved" and r["x_25832"] and r["quality_status"] == "ok"
    assert r["raw_payload"] == n and len(r["content_hash"]) == 64


def test_ambiguous_location_is_warning(gaz):
    r = normalize(notice(nuts=("DEA11", "DEA22")), ["transformers"], gaz)
    assert r["location_note"] == "ambiguous_multiple_nuts3" and r["quality_status"] == "warning" and r["x_25832"] is None


def test_missing_fields_make_record_invalid(gaz):
    r = normalize({"publication-number": "9-2026", "publication-date": "garbage"}, [], gaz)
    assert r["quality_status"] == "invalid"
    assert {"missing_title", "missing_or_invalid_publication_date", "missing_cpv"} <= set(r["quality_issues"])


@pytest.mark.parametrize("bad", [None, "s", [], {}, {"publication-number": "  "}, {"publication-number": 5}])
def test_unkeyable_records_rejected(gaz, bad):
    with pytest.raises(RejectedRecord):
        normalize(bad, [], gaz)


def test_hash_stable_and_content_sensitive(gaz):
    n = notice()
    assert normalize(n, ["a"], gaz)["content_hash"] == normalize(dict(n), ["a"], gaz)["content_hash"]
    assert normalize({**n, "notice-title": {"eng": "changed"}}, ["a"], gaz)["content_hash"] != normalize(n, ["a"], gaz)["content_hash"]
