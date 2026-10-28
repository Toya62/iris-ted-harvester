import logging
import time

import requests

from .config import API_URL, FIELDS

log = logging.getLogger(__name__)


class TedError(Exception):
    pass


def _post(session, payload, retries=4, backoff=1.5):
    last = None
    for attempt in range(retries + 1):
        try:
            r = session.post(API_URL, json=payload, timeout=30)
        except requests.RequestException as e:
            last = e
        else:
            if r.status_code == 200:
                if "json" not in r.headers.get("Content-Type", "").lower():
                    raise TedError(f"non-JSON response ({r.headers.get('Content-Type')})")
                try:
                    data = r.json()
                except ValueError as e:
                    raise TedError(f"invalid JSON: {e}") from e
                if not isinstance(data, dict) or not isinstance(data.get("notices"), list):
                    raise TedError("malformed response: 'notices' list missing")
                return data
            if r.status_code in (429, 500, 502, 503, 504):
                last = TedError(f"HTTP {r.status_code}")
            else:
                raise TedError(f"HTTP {r.status_code}: {r.text[:200]}")
        if attempt < retries:
            time.sleep(backoff ** attempt)
    raise TedError(f"giving up after {retries + 1} attempts: {last}")


def search(query, session=None, page_size=100, max_records=None, max_pages=1000):
    """Yield raw notices using token (iteration) pagination."""
    session = session or requests.Session()
    token, seen, pages = None, 0, 0
    while pages < max_pages:
        payload = {"query": query, "fields": FIELDS, "limit": page_size, "paginationMode": "ITERATION"}
        if token:
            payload["iterationNextToken"] = token
        data = _post(session, payload)
        pages += 1
        notices = data["notices"]
        if not notices:
            return
        for n in notices:
            yield n
            seen += 1
            if max_records and seen >= max_records:
                return
        token = data.get("iterationNextToken")
        if not token:
            return
