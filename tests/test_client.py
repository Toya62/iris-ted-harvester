import pytest
import requests
from conftest import make_client, notice, page, resp
from ted_harvester.client import TedApiError, TedFormatError


def test_token_pagination(settings):
    c, s = make_client(settings, [resp(page([notice("1-2026")], "T2")), resp(page([notice("2-2026")]))])
    assert [n["publication-number"] for n in c.search("q")] == ["1-2026", "2-2026"]
    assert s.post.call_args_list[1].kwargs["json"]["iterationNextToken"] == "T2"
    assert "iterationNextToken" not in s.post.call_args_list[0].kwargs["json"]


def test_empty_response(settings):
    c, _ = make_client(settings, [resp(page([]))])
    assert list(c.search("q")) == []


def test_retries_network_errors(settings):
    c, s = make_client(settings, [requests.ConnectionError("x"), requests.Timeout("y"), resp(page([]))])
    assert list(c.search("q")) == [] and s.post.call_count == 3


def test_gives_up_on_5xx_and_429(settings):
    c, s = make_client(settings, [resp({}, 503), resp({}, 429, {"Retry-After": "1"}), resp({}, 500), resp({}, 502)])
    with pytest.raises(TedApiError, match="Giving up"):
        list(c.search("q"))
    assert s.post.call_count == settings.max_retries + 1


def test_obsolete_endpoint_202_is_format_error(settings):
    c, _ = make_client(settings, [resp(text="", status=202)])
    with pytest.raises(TedFormatError):
        list(c.search("q"))


def test_html_and_malformed_bodies(settings):
    c, _ = make_client(settings, [resp(text="<html>maintenance</html>")])
    with pytest.raises(TedFormatError):
        list(c.search("q"))
    c, _ = make_client(settings, [resp({"unexpected": 1})])
    with pytest.raises(TedFormatError):
        list(c.search("q"))


def test_400_not_retried(settings):
    c, s = make_client(settings, [resp({"message": "bad"}, 400)])
    with pytest.raises(TedApiError):
        list(c.search("q"))
    assert s.post.call_count == 1


def test_repeated_token_aborts(settings):
    p = page([notice("1-2026")], "SAME")
    c, _ = make_client(settings, [resp(p), resp(p), resp(p)])
    with pytest.raises(TedApiError, match="token repeated"):
        list(c.search("q"))
