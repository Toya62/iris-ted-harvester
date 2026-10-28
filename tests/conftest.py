import json
from unittest.mock import MagicMock
import pytest
from ted_harvester.config import Settings
from ted_harvester.geo import NutsGazetteer

GAZ_ROWS = {"DEA13": ("7.0", "51.45"), "DEA11": ("6.78", "51.23"), "DEA22": ("7.1", "50.73"),
            "DEB11": ("200", "95"), "DEA99": ("0", "0"), "FR104": ("2.3", "48.5")}


def notice(pid="100001-2026", nuts=("DEA13",), title=None, date="2026-10-01+02:00", cpv=("31321300",)):
    return {"publication-number": pid, "notice-title": title or {"eng": f"Germany – cable {pid}"},
            "publication-date": date, "notice-type": "cn-standard", "place-of-performance": list(nuts),
            "place-of-performance-country-proc": ["DEU"], "classification-cpv": list(cpv),
            "buyer-name": {"deu": ["Stadtwerke"]}, "estimated-value-proc": "1000.5",
            "links": {"html": {"ENG": f"https://ted.europa.eu/en/notice/-/detail/{pid}"}}}


def page(notices, token=None):
    return {"notices": notices, "totalNoticeCount": len(notices), "iterationNextToken": token, "timedOut": False}


def resp(body=None, status=200, headers=None, text=None):
    r = MagicMock()
    r.status_code, r.headers = status, headers or {}
    r.text = text if text is not None else json.dumps(body)
    if text is not None:
        r.json.side_effect = ValueError("not json")
    else:
        r.json.return_value = body
    return r


def make_client(settings, responses):
    from ted_harvester.client import TedClient
    s = MagicMock()
    s.headers = {}
    s.post.side_effect = responses
    return TedClient(settings, session=s, sleep=lambda _: None), s


@pytest.fixture
def settings():
    return Settings(countries=("DEU",), max_retries=3, backoff_base_s=0)


@pytest.fixture
def gaz():
    return NutsGazetteer(GAZ_ROWS)
