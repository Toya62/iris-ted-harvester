import pytest
import requests

from ted_harvester import client, geo
from ted_harvester.cli import harvest
from ted_harvester.load import upsert
from ted_harvester.normalize import merge, normalize

CENT = {"DEA18": (7.19, 51.18), "FR104": (2.2, 48.8)}


def notice(pid="1-2026", nuts=("DEA18",), title=None):
    return {"publication-number": pid, "notice-title": title or {"eng": "Cable"}, "publication-date": "2026-10-01+02:00",
            "place-of-performance": list(nuts), "buyer-country": ["DEU"]}


class Resp:
    def __init__(self, status=200, body=None, ctype="application/json"):
        self.status_code, self._b, self.headers, self.text = status, body, {"Content-Type": ctype}, "x"

    def json(self):
        if self._b is None:
            raise ValueError("bad")
        return self._b


class Sess:
    def __init__(self, items):
        self.items = list(items)
        self.calls = 0

    def post(self, url, json=None, timeout=None):
        self.calls += 1
        it = self.items.pop(0)
        if isinstance(it, Exception):
            raise it
        return it


@pytest.fixture(autouse=True)
def nosleep(monkeypatch):
    monkeypatch.setattr(client.time, "sleep", lambda s: None)


def test_pagination_follows_token():
    s = Sess([Resp(body={"notices": [notice("1")], "iterationNextToken": "t"}), Resp(body={"notices": [notice("2")]})])
    assert [n["publication-number"] for n in client.search("q", session=s)] == ["1", "2"]


def test_empty_response():
    assert list(client.search("q", session=Sess([Resp(body={"notices": []})]))) == []


def test_retry_then_success():
    s = Sess([requests.ConnectionError("x"), Resp(503), Resp(body={"notices": [notice()]})])
    assert len(list(client.search("q", session=s))) == 1 and s.calls == 3


def test_html_202_rejected():
    with pytest.raises(client.TedError):
        list(client.search("q", session=Sess([Resp(202, None, "text/html")])))


def test_malformed_json_rejected():
    with pytest.raises(client.TedError):
        list(client.search("q", session=Sess([Resp(body={"oops": 1})])))


def test_geo_single_region_resolves():
    x, y, st, _ = geo.resolve(["DEA18", "DE"], CENT)
    assert st == "resolved" and 300000 < x < 500000 and 5600000 < y < 5800000


def test_geo_ambiguous_and_coarse():
    assert geo.resolve(["DEA18", "FR104"], CENT)[2] == "ambiguous"
    assert geo.resolve(["DE", "DEA"], CENT)[2] == "unresolved"


def test_invalid_coordinates_rejected():
    for bad in [(float("nan"), 50), (200, 50), (7, 95)]:
        with pytest.raises(ValueError):
            geo.to_25832(*bad)
    assert geo.resolve(["XX999"], {"XX999": (500.0, 10.0)})[2] == "unresolved"


def test_normalize_missing_fields_visible():
    rec, iss = normalize({"publication-number": "9"}, "grid_cabling", CENT)
    assert "missing title" in iss and "missing publication-date" in iss
    assert normalize({}, "grid_cabling", CENT)[0] is None


def test_duplicates_merge_signal_types():
    a, _ = normalize(notice("1"), "grid_cabling", CENT)
    b, _ = normalize(notice("1"), "transformers", CENT)
    m = merge([a, b])
    assert len(m) == 1 and m[0]["signal_types"] == ["grid_cabling", "transformers"]


class FakeCur:
    def __init__(self, db):
        self.db, self.row = db, None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, p):
        old = self.db.get(p["source_record_id"])
        if old is None:
            self.db[p["source_record_id"]] = p["content_hash"]
            self.row = (True,)
        elif old != p["content_hash"]:
            self.db[p["source_record_id"]] = p["content_hash"]
            self.row = (False,)
        else:
            self.row = None

    def fetchone(self):
        return self.row


class FakeConn:
    def __init__(self):
        self.db = {}

    def cursor(self):
        return FakeCur(self.db)

    def commit(self):
        pass


def test_rerun_is_idempotent():
    recs = merge([normalize(notice(str(i)), "grid_cabling", CENT)[0] for i in range(3)])
    conn = FakeConn()
    assert upsert(conn, recs) == {"inserted": 3, "updated": 0, "unchanged": 0}
    assert upsert(conn, recs) == {"inserted": 0, "updated": 0, "unchanged": 3}
    assert len(conn.db) == 3


def test_harvest_reports_category_error(monkeypatch):
    def boom(*a, **k):
        raise client.TedError("down")
        yield
    monkeypatch.setattr(client, "search", boom)
    from datetime import date
    recs, rep = harvest(date(2026, 10, 1), None, CENT, 5)
    assert recs == [] and len(rep["category_errors"]) == 3
