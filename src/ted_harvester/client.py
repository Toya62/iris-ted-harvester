"""HTTP client for querying Tenders Electronic Daily (TED) API v3."""

import logging
import time
from typing import Any, Dict, Iterator, Optional

import requests

from .config import API_URL, FIELDS

logger = logging.getLogger(__name__)


class TedError(Exception):
    """Base exception for TED API harvesting errors."""


class TedApiError(TedError):
    """Raised when the TED API returns an unrecoverable HTTP status or reaches max retries."""


class TedFormatError(TedError):
    """Raised when the TED API returns unexpected HTML, malformed JSON, or invalid schema."""


def post_with_retries(
    session: requests.Session,
    payload: Dict[str, Any],
    max_retries: int = 4,
    backoff_factor: float = 1.5,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    Execute POST request against TED search endpoint with exponential backoff for transient errors.
    """
    last_error: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        try:
            response = session.post(API_URL, json=payload, timeout=timeout)
        except requests.RequestException as exc:
            last_error = exc
            logger.warning(
                "Request error on attempt %d/%d: %s",
                attempt + 1,
                max_retries + 1,
                exc,
            )
        else:
            status = response.status_code
            content_type = response.headers.get("Content-Type", "").lower()

            if status == 200:
                if "json" not in content_type:
                    raise TedFormatError(
                        f"Expected application/json response but received '{content_type}'"
                    )
                try:
                    data = response.json()
                except ValueError as exc:
                    raise TedFormatError(f"Failed to decode response JSON: {exc}") from exc

                if not isinstance(data, dict) or not isinstance(data.get("notices"), list):
                    raise TedFormatError("Response missing required 'notices' array")

                return data

            # Retry transient server errors and rate limits
            if status in (429, 500, 502, 503, 504):
                last_error = TedApiError(f"HTTP {status}")
                logger.warning(
                    "Received HTTP %d on attempt %d/%d. Retrying...",
                    status,
                    attempt + 1,
                    max_retries + 1,
                )
            else:
                # Fatal client errors (400, 401, 403, 404) or obsolete endpoints (202)
                preview = response.text[:200].strip()
                raise TedApiError(f"TED API request failed with HTTP {status}: {preview}")

        if attempt < max_retries:
            sleep_time = backoff_factor ** attempt
            time.sleep(sleep_time)

    raise TedApiError(f"TED request failed after {max_retries + 1} attempts. Last error: {last_error}")


def search(
    query: str,
    session: Optional[requests.Session] = None,
    page_size: int = 100,
    max_records: Optional[int] = None,
    max_pages: int = 1000,
) -> Iterator[Dict[str, Any]]:
    """
    Iterate over procurement notices matching a query using TED token-based pagination.
    """
    session = session or requests.Session()
    next_token: Optional[str] = None
    records_yielded = 0
    pages_fetched = 0

    while pages_fetched < max_pages:
        payload: Dict[str, Any] = {
            "query": query,
            "fields": FIELDS,
            "limit": page_size,
            "paginationMode": "ITERATION",
        }
        if next_token:
            payload["iterationNextToken"] = next_token

        data = post_with_retries(session, payload)
        pages_fetched += 1

        notices = data.get("notices", [])
        if not notices:
            logger.debug("Received empty notice list, ending iteration.")
            return

        for notice in notices:
            yield notice
            records_yielded += 1
            if max_records and records_yielded >= max_records:
                return

        next_token = data.get("iterationNextToken")
        if not next_token:
            logger.debug("No next page token returned, pagination complete.")
            return
