"""Normalization and deduplication of raw TED notices into staging signal records."""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from .config import SOURCE_SYSTEM
from .geo import resolve

logger = logging.getLogger(__name__)


def extract_title(raw_title: Any) -> Optional[str]:
    """
    Extract best available title from notice title field.
    Prefers English, falls back to German, then first available localized string.
    """
    if isinstance(raw_title, str):
        cleaned = raw_title.strip()
        return cleaned if cleaned else None

    if isinstance(raw_title, dict) and raw_title:
        # Check preferred languages
        for lang_key in ("eng", "ENG", "deu", "DEU"):
            if lang_key in raw_title and raw_title[lang_key]:
                val = raw_title[lang_key]
                return val if isinstance(val, str) else str(val[0])

        # Fallback to first available language dictionary entry
        for val in raw_title.values():
            if isinstance(val, str) and val.strip():
                return val.strip()
            if isinstance(val, list) and val:
                return str(val[0]).strip()

    return None


def extract_url(notice: Dict[str, Any], publication_number: str) -> str:
    """
    Extract official web link to notice detail page.
    Checks htmlDirect and html link dictionaries, falling back to canonical TED URL.
    """
    links = notice.get("links") or {}
    html_links = links.get("htmlDirect") or links.get("html") or {}

    for lang in ("ENG", "DEU"):
        if lang in html_links and isinstance(html_links[lang], str):
            return html_links[lang]

    for fallback_url in html_links.values():
        if isinstance(fallback_url, str) and fallback_url.startswith("http"):
            return fallback_url

    return f"https://ted.europa.eu/en/notice/-/detail/{publication_number}"


def extract_publication_date(raw_date: Any) -> Optional[str]:
    """Extract standard ISO date (YYYY-MM-DD) from TED publication-date timestamp."""
    if isinstance(raw_date, str) and len(raw_date.strip()) >= 10:
        return raw_date.strip()[:10]
    return None


def ensure_list(value: Any) -> List[Any]:
    """Coerce single values or None into a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def normalize(
    notice: Dict[str, Any],
    signal_type: str,
    centroids: Dict[str, Tuple[float, float]],
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """
    Normalize raw TED notice payload into staging schema record.

    Returns:
      (record, list_of_quality_issues)
      record will be None if the notice lacks a valid publication number.
    """
    issues: List[str] = []

    publication_number = notice.get("publication-number")
    if not publication_number or not isinstance(publication_number, str) or not publication_number.strip():
        return None, ["missing publication-number"]

    publication_number = publication_number.strip()

    title = extract_title(notice.get("notice-title"))
    if not title:
        issues.append("missing title")

    published_at = extract_publication_date(notice.get("publication-date"))
    if not published_at:
        issues.append("missing publication-date")

    raw_nuts = ensure_list(notice.get("place-of-performance"))
    nuts_codes = [str(code).strip() for code in raw_nuts if isinstance(code, str) and code.strip()]

    raw_buyer_countries = ensure_list(notice.get("buyer-country"))
    buyer_country = next((str(c).strip() for c in raw_buyer_countries if isinstance(c, str) and c.strip()), None)

    country_code = buyer_country or (nuts_codes[0][:2] if nuts_codes else None)

    x_coord, y_coord, geo_status, geo_note = resolve(nuts_codes, centroids)

    record: Dict[str, Any] = {
        "source_system": SOURCE_SYSTEM,
        "source_record_id": publication_number,
        "signal_types": [signal_type],
        "title": title,
        "published_at": published_at,
        "source_url": extract_url(notice, publication_number),
        "country_code": country_code,
        "nuts_codes": nuts_codes,
        "x": x_coord,
        "y": y_coord,
        "geo_status": geo_status,
        "geo_note": geo_note,
        "raw": notice,
    }

    return record, issues


def content_hash(record: Dict[str, Any]) -> str:
    """
    Compute deterministic SHA-256 hash of core payload fields to detect changes on ingestion.
    """
    tracked_fields = (
        "signal_types",
        "title",
        "published_at",
        "source_url",
        "nuts_codes",
        "x",
        "y",
        "geo_status",
    )
    core_payload = {key: record.get(key) for key in tracked_fields}
    serialized = json.dumps(core_payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def merge(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deduplicate records by (source_system, source_record_id) and union signal types.
    Updates content_hash on all resulting unique records.
    """
    merged_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for record in records:
        key = (record["source_system"], record["source_record_id"])
        if key in merged_map:
            existing = merged_map[key]
            combined_types = set(existing["signal_types"]) | set(record["signal_types"])
            existing["signal_types"] = sorted(combined_types)
        else:
            merged_map[key] = record

    results: List[Dict[str, Any]] = []
    for record in merged_map.values():
        record["content_hash"] = content_hash(record)
        results.append(record)

    return results
