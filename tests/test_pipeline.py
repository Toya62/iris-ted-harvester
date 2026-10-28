"""Unit tests for the TED harvester pipeline components."""

from datetime import date
import pytest
import requests

from ted_harvester import client, config, geo
from ted_harvester.cli import harvest
from ted_harvester.load import upsert
from ted_harvester.normalize import merge, normalize

# Sample NUTS-3 centroids for test assertions
SAMPLE_CENTROIDS = {
    "DEA18": (7.19, 51.18),  # Remscheid, Germany
    "FR104": (2.20, 48.80),  # Essonne, France
}


def build_raw_notice(
    notice_id: str = "100001-2026",
    nuts_codes=("DEA18",),
    title: dict = None,
    pub_date: str = "2026-10-01+02:00",
) -> dict:
    """Helper to construct raw TED notice payloads for testing."""
    return {
        "publication-number": notice_id,
        "notice-title": title or {"eng": f"Germany - High voltage infrastructure {notice_id}"},
        "publication-date": pub_date,
        "place-of-performance": list(nuts_codes),
        "buyer-country": ["DEU"],
        "links": {
            "htmlDirect": {
                "ENG": f"https://ted.europa.eu/en/notice/{notice_id}/html"
            }
        },
    }


class MockResponse:
    """Simulated requests.Response object."""

    def __init__(
        self,
        status_code: int = 200,
        json_data: dict = None,
        content_type: str = "application/json",
        text: str = "Mock response body",
    ):
        self.status_code = status_code
        self._json_data = json_data
        self.headers = {"Content-Type": content_type}
        self.text = text

    def json(self):
        if self._json_data is None:
            raise ValueError("Response body does not contain valid JSON")
        return self._json_data


class MockSession:
    """Simulated requests.Session with a queued sequence of responses or exceptions."""

    def __init__(self, responses):
        self.queue = list(responses)
        self.call_count = 0

    def post(self, url, json=None, timeout=None):
        self.call_count += 1
        if not self.queue:
            raise RuntimeError("MockSession ran out of queued responses")
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def disable_sleep(monkeypatch):
    """Bypass time.sleep in all tests to ensure rapid test suite execution."""
    monkeypatch.setattr(client.time, "sleep", lambda _: None)


# =========================================================================
# Client & HTTP Search Tests
# =========================================================================

def test_pagination_follows_iteration_token():
    """Verify pagination correctly follows iterationNextToken until exhaustion."""
    first_page = MockResponse(
        json_data={
            "notices": [build_raw_notice("notice-1")],
            "iterationNextToken": "page-2-token",
        }
    )
    second_page = MockResponse(
        json_data={
            "notices": [build_raw_notice("notice-2")],
            "iterationNextToken": None,
        }
    )
    session = MockSession([first_page, second_page])

    results = list(client.search("test query", session=session))

    assert len(results) == 2
    assert [n["publication-number"] for n in results] == ["notice-1", "notice-2"]
    assert session.call_count == 2


def test_empty_response_handling():
    """Verify client terminates cleanly when an empty notice array is returned."""
    empty_page = MockResponse(json_data={"notices": []})
    session = MockSession([empty_page])

    results = list(client.search("empty query", session=session))

    assert results == []
    assert session.call_count == 1


def test_retry_on_transient_failure_then_success():
    """Verify client retries on connection error and HTTP 503 before succeeding."""
    session = MockSession([
        requests.ConnectionError("Connection reset"),
        MockResponse(status_code=503),
        MockResponse(json_data={"notices": [build_raw_notice("notice-ok")]}),
    ])

    results = list(client.search("query", session=session))

    assert len(results) == 1
    assert session.call_count == 3


def test_obsolete_html_202_endpoint_rejected():
    """Verify obsolete endpoint returning HTML 202 is rejected with TedError."""
    session = MockSession([MockResponse(status_code=202, content_type="text/html")])

    with pytest.raises(client.TedError):
        list(client.search("query", session=session))


def test_malformed_json_response_rejected():
    """Verify response missing required 'notices' field raises TedError."""
    session = MockSession([MockResponse(json_data={"unexpected": "payload"})])

    with pytest.raises(client.TedError):
        list(client.search("query", session=session))


# =========================================================================
# Geospatial & Projection Tests
# =========================================================================

def test_single_nuts3_region_resolves_to_25832():
    """Verify a notice with exactly one NUTS-3 code resolves to EPSG:25832 coordinates."""
    x, y, status, note = geo.resolve(["DEA18", "DEU"], SAMPLE_CENTROIDS)

    assert status == "resolved"
    assert "DEA18" in note
    assert 300000 < x < 500000
    assert 5600000 < y < 5800000


def test_ambiguous_and_coarse_locations():
    """Verify multiple NUTS-3 codes become ambiguous and coarse regions stay unresolved."""
    _, _, status_ambig, _ = geo.resolve(["DEA18", "FR104"], SAMPLE_CENTROIDS)
    assert status_ambig == "ambiguous"

    _, _, status_coarse, _ = geo.resolve(["DE", "DEA"], SAMPLE_CENTROIDS)
    assert status_coarse == "unresolved"


def test_invalid_coordinates_rejected():
    """Verify invalid coordinates (NaN, out-of-Europe bounds) raise errors."""
    for bad_lon, bad_lat in [(float("nan"), 50.0), (200.0, 50.0), (7.0, 95.0)]:
        with pytest.raises(ValueError):
            geo.to_25832(bad_lon, bad_lat)

    # Unknown region not in centroids table stays unresolved
    _, _, status, note = geo.resolve(["XX999"], {"XX999": (500.0, 10.0)})
    assert status == "unresolved"
    assert "invalid coordinate" in note


def test_load_centroids_from_csv(tmp_path):
    """Verify parsing centroid coordinates from CSV file."""
    csv_file = tmp_path / "centroids.csv"
    csv_file.write_text("nuts_id,lon,lat\nDEA18,7.19,51.18\n", encoding="utf-8")

    loaded = geo.load_centroids(str(csv_file))
    assert loaded == {"DEA18": (7.19, 51.18)}


# =========================================================================
# Normalization & Deduplication Tests
# =========================================================================

def test_missing_fields_visible_in_quality_issues():
    """Verify missing title or date is flagged in record quality issues."""
    notice = {"publication-number": "incomplete-01"}
    record, issues = normalize(notice, "grid_cabling", SAMPLE_CENTROIDS)

    assert record is not None
    assert "missing title" in issues
    assert "missing publication-date" in issues

    # Notice with no identifier is rejected entirely
    empty_notice = {}
    record_none, issues_none = normalize(empty_notice, "grid_cabling", SAMPLE_CENTROIDS)
    assert record_none is None
    assert "missing publication-number" in issues_none


def test_duplicates_merged_and_signal_types_unioned():
    """Verify multiple hits for the same notice ID merge with unioned signal_types."""
    record_a, _ = normalize(build_raw_notice("shared-1"), "grid_cabling", SAMPLE_CENTROIDS)
    record_b, _ = normalize(build_raw_notice("shared-1"), "transformers", SAMPLE_CENTROIDS)

    merged = merge([record_a, record_b])

    assert len(merged) == 1
    assert merged[0]["signal_types"] == ["grid_cabling", "transformers"]


def test_url_fallback_resolution():
    """Verify URL fallback logic across htmlDirect, html, and detail template."""
    notice_direct = {
        "publication-number": "p1",
        "links": {"htmlDirect": {"ENG": "https://ted.europa.eu/direct"}},
    }
    rec_direct, _ = normalize(notice_direct, "grid_cabling", SAMPLE_CENTROIDS)
    assert rec_direct["source_url"] == "https://ted.europa.eu/direct"

    notice_html = {
        "publication-number": "p2",
        "links": {"html": {"DEU": "https://ted.europa.eu/deu"}},
    }
    rec_html, _ = normalize(notice_html, "grid_cabling", SAMPLE_CENTROIDS)
    assert rec_html["source_url"] == "https://ted.europa.eu/deu"

    notice_default = {"publication-number": "p3"}
    rec_default, _ = normalize(notice_default, "grid_cabling", SAMPLE_CENTROIDS)
    assert rec_default["source_url"] == "https://ted.europa.eu/en/notice/-/detail/p3"


def test_content_hash_sensitivity():
    """Verify content hash changes when payload attributes change."""
    rec1, _ = normalize(build_raw_notice("1", title={"eng": "Title A"}), "grid_cabling", SAMPLE_CENTROIDS)
    rec2, _ = normalize(build_raw_notice("1", title={"eng": "Title A"}), "grid_cabling", SAMPLE_CENTROIDS)
    rec3, _ = normalize(build_raw_notice("1", title={"eng": "Title B"}), "grid_cabling", SAMPLE_CENTROIDS)

    m1 = merge([rec1])[0]
    m2 = merge([rec2])[0]
    m3 = merge([rec3])[0]

    assert m1["content_hash"] == m2["content_hash"]
    assert m1["content_hash"] != m3["content_hash"]


# =========================================================================
# Database Idempotency & Pipeline Tests
# =========================================================================

class MockDatabaseCursor:
    """Simulated database cursor mimicking PostgreSQL upsert behavior."""

    def __init__(self, storage):
        self.storage = storage
        self.last_result = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params):
        record_id = params["source_record_id"]
        new_hash = params["content_hash"]
        current_hash = self.storage.get(record_id)

        if current_hash is None:
            # New insert -> returns is_new_insert = True
            self.storage[record_id] = new_hash
            self.last_result = (True,)
        elif current_hash != new_hash:
            # Update -> returns is_new_insert = False
            self.storage[record_id] = new_hash
            self.last_result = (False,)
        else:
            # Unchanged -> ON CONFLICT WHERE skips, no row returned
            self.last_result = None

    def fetchone(self):
        return self.last_result


class MockDatabaseConnection:
    """Simulated database connection."""

    def __init__(self):
        self.storage = {}

    def cursor(self):
        return MockDatabaseCursor(self.storage)

    def commit(self):
        pass


def test_rerun_is_strictly_idempotent():
    """Verify loading identical records twice produces 0 inserts and 0 updates on re-run."""
    records = merge([
        normalize(build_raw_notice(f"batch-{i}"), "grid_cabling", SAMPLE_CENTROIDS)[0]
        for i in range(3)
    ])
    conn = MockDatabaseConnection()

    first_run = upsert(conn, records)
    assert first_run == {"inserted": 3, "updated": 0, "unchanged": 0}

    second_run = upsert(conn, records)
    assert second_run == {"inserted": 0, "updated": 0, "unchanged": 3}
    assert len(conn.storage) == 3


def test_pipeline_reports_category_errors(monkeypatch):
    """Verify transient category failures are caught and recorded in the report."""
    def simulate_failure(*args, **kwargs):
        raise client.TedError("TED API service unavailable")
        yield  # Make it a generator

    monkeypatch.setattr(client, "search", simulate_failure)

    records, report = harvest(
        since=date(2026, 10, 1),
        until=None,
        centroids=SAMPLE_CENTROIDS,
        per_category=5,
    )

    assert records == []
    assert len(report["category_errors"]) == 3
    assert "grid_cabling" in report["category_errors"]


def test_config_query_syntax():
    """Verify search queries contain expected CPV prefixes and date constraints."""
    queries = config.queries(date(2026, 10, 1), date(2026, 10, 31))

    assert "grid_cabling" in queries
    assert "transformers" in queries
    assert "public_data_centre" in queries

    assert "3132*" in queries["grid_cabling"]
    assert "3117*" in queries["transformers"]
    assert "data centre" in queries["public_data_centre"]
    assert "publication-date>=20261001 AND publication-date<=20261031" in queries["grid_cabling"]
