"""Map a raw TED notice to a staging record dict. Missing fields are recorded as quality issues, never invented."""
from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

from .domain import SIGNAL_TYPE
from .geo import NutsGazetteer, nuts_codes, resolve_location


class RejectedRecord(ValueError):
    pass


def pick(v, prefer=("eng", "deu")):
    """Return (text, lang) from a TED multilingual value (dict of lang -> str|list) or a plain str/list."""
    if isinstance(v, dict):
        for lang in (*prefer, *v):
            x = v.get(lang)
            x = x[0] if isinstance(x, list) and x else x
            if isinstance(x, str) and x.strip():
                return x.strip(), lang
        return None, None
    if isinstance(v, list):
        v = v[0] if v else None
    return (v.strip(), None) if isinstance(v, str) and v.strip() else (None, None)


def _list(v) -> list[str]:
    if isinstance(v, str):
        v = [v]
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []


def _date(v):
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def normalize(notice: Any, categories: list[str], gaz: NutsGazetteer) -> dict:
    if not isinstance(notice, dict):
        raise RejectedRecord("not_an_object")
    pid = notice.get("publication-number")
    if not isinstance(pid, str) or not pid.strip():
        raise RejectedRecord("missing_publication_number")
    pid = pid.strip()
    title, lang = pick(notice.get("notice-title"))
    pub = _date(notice.get("publication-date"))
    cpv = sorted(set(_list(notice.get("classification-cpv"))))
    places = _list(notice.get("place-of-performance"))
    loc = resolve_location(places, gaz)
    html = (notice.get("links") or {}).get("html") if isinstance(notice.get("links"), dict) else None
    url, _ = pick(html, prefer=("ENG", "DEU"))
    countries = _list(notice.get("place-of-performance-country-proc")) or _list(notice.get("buyer-country"))
    buyer, _ = pick(notice.get("buyer-name"))
    city, _ = pick(notice.get("place-of-performance-city-proc"))

    issues = []
    if not title:
        issues.append("missing_title")
    if pub is None:
        issues.append("missing_or_invalid_publication_date")
    if not cpv:
        issues.append("missing_cpv")
    if loc.status == "unresolved":
        issues.append(f"location_unresolved:{loc.reason}")
    if loc.warning:
        issues.append(loc.warning)
    invalid = {"missing_title", "missing_or_invalid_publication_date"} & set(issues)
    rec = {
        "source_system": "TED", "source_record_id": pid, "signal_type": SIGNAL_TYPE,
        "signal_categories": sorted(set(categories)), "title": title, "title_lang": lang,
        "publication_date": pub, "source_url": url or f"https://ted.europa.eu/en/notice/-/detail/{pid}",
        "notice_type": notice.get("notice-type") if isinstance(notice.get("notice-type"), str) else None,
        "buyer_name": buyer, "country_code": countries[0] if countries else None,
        "nuts_codes": nuts_codes(places), "place_text": city, "cpv_codes": cpv,
        "estimated_value": _num(notice.get("estimated-value-proc")),
        "location_status": loc.status, "location_note": loc.reason,
        "lon_4326": loc.lon, "lat_4326": loc.lat, "x_25832": loc.x, "y_25832": loc.y,
        "quality_status": "invalid" if invalid else ("warning" if issues else "ok"),
        "quality_issues": issues, "raw_payload": notice,
    }
    body = {k: v for k, v in rec.items() if k != "raw_payload"}
    rec["content_hash"] = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
    return rec
