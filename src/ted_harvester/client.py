"""TED Search API v3 client: token pagination, retries with backoff, strict response validation."""
from __future__ import annotations

import logging
import random
import time
from typing import Any, Callable, Iterator

import requests

from .config import Settings
from .domain import FIELDS

log = logging.getLogger(__name__)
RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}


class TedApiError(RuntimeError):
    """Exhausted retries or non-retryable API failure."""


class TedFormatError(TedApiError):
    """Response is not the documented v3 JSON (e.g. the obsolete /api/v2.0 URL answers HTTP 202 without JSON)."""


class TedClient:
    def __init__(self, settings: Settings, session=None, sleep: Callable[[float], None] = time.sleep):
        self.s = settings
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": settings.user_agent, "Accept": "application/json"})
        self._sleep = sleep

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        last: Exception | None = None
        for attempt in range(self.s.max_retries + 1):
            try:
                resp = self.session.post(self.s.api_url, json=body, timeout=self.s.timeout_s)
            except (requests.ConnectionError, requests.Timeout) as exc:
                last = exc
                log.warning("network error (attempt %d): %s", attempt + 1, exc)
            else:
                if resp.status_code in RETRY_STATUS:
                    last = TedApiError(f"HTTP {resp.status_code}")
                    log.warning("retryable HTTP %s (attempt %d)", resp.status_code, attempt + 1)
                    ra = resp.headers.get("Retry-After", "")
                    if ra.isdigit() and attempt < self.s.max_retries:
                        self._sleep(min(int(ra), 60))
                        continue
                elif resp.status_code != 200:
                    msg = f"HTTP {resp.status_code} from {self.s.api_url}: {resp.text[:300]!r}"
                    raise (TedFormatError if resp.status_code < 400 else TedApiError)(msg)
                else:
                    try:
                        data = resp.json()
                    except ValueError as exc:
                        raise TedFormatError(f"Response is not JSON: {resp.text[:200]!r}") from exc
                    if not isinstance(data, dict) or not isinstance(data.get("notices"), list):
                        raise TedFormatError("Response has no 'notices' array")
                    if data.get("timedOut"):
                        last = TedApiError("API reported timedOut=true")
                    else:
                        return data
            if attempt < self.s.max_retries:
                self._sleep(self.s.backoff_base_s * (2 ** attempt) + random.uniform(0, 0.25))
        raise TedApiError(f"Giving up after {self.s.max_retries + 1} attempts: {last}")

    def search(self, query: str) -> Iterator[dict[str, Any]]:
        token, seen, total, n = None, set(), None, 0
        while True:
            body: dict[str, Any] = {"query": query, "fields": list(FIELDS), "limit": self.s.page_limit,
                                    "paginationMode": "ITERATION"}
            if token:
                body["iterationNextToken"] = token
            data = self._post(body)
            total = data.get("totalNoticeCount", total)
            if not data["notices"]:
                break
            for notice in data["notices"]:
                n += 1
                yield notice
            token = data.get("iterationNextToken")
            if not token:
                break
            if token in seen:
                raise TedApiError("Pagination token repeated; aborting")
            seen.add(token)
        if total is not None and n < total:
            log.warning("fetched %d of %s reported notices", n, total)
