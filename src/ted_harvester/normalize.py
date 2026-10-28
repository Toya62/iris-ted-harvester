import hashlib
import json

from .config import SOURCE_SYSTEM
from .geo import resolve


def _title(v):
    if isinstance(v, str):
        return v
    if isinstance(v, dict) and v:
        for k in ("eng", "ENG", "deu", "DEU"):
            if v.get(k):
                return v[k] if isinstance(v[k], str) else str(v[k][0])
        first = next(iter(v.values()))
        return first if isinstance(first, str) else (str(first[0]) if first else None)
    return None


def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _url(n, pid):
    links = n.get("links") or {}
    html = links.get("htmlDirect") or links.get("html") or {}
    for k in ("ENG", "DEU"):
        if html.get(k):
            return html[k]
    for v in html.values():
        if isinstance(v, str) and v:
            return v
    return f"https://ted.europa.eu/en/notice/-/detail/{pid}"


def normalize(notice, category, centroids):
    """Return (record, issues). Returns (None, issues) if the notice has no identifier."""
    issues = []
    pid = notice.get("publication-number")
    if not pid or not isinstance(pid, str):
        return None, ["missing publication-number"]
    title = _title(notice.get("notice-title"))
    if not title:
        issues.append("missing title")
    pub = notice.get("publication-date")
    pub = pub[:10] if isinstance(pub, str) and len(pub) >= 10 else None
    if not pub:
        issues.append("missing publication-date")
    nuts = [c for c in _as_list(notice.get("place-of-performance")) if isinstance(c, str)]
    country = next(iter(_as_list(notice.get("buyer-country"))), None) or (nuts[0][:2] if nuts else None)
    x, y, status, note = resolve(nuts, centroids)
    rec = {
        "source_system": SOURCE_SYSTEM, "source_record_id": pid, "signal_types": [category],
        "title": title, "published_at": pub, "source_url": _url(notice, pid),
        "country_code": country, "nuts_codes": nuts, "x": x, "y": y,
        "geo_status": status, "geo_note": note, "raw": notice,
    }
    return rec, issues


def content_hash(rec):
    core = {k: rec[k] for k in ("signal_types", "title", "published_at", "source_url", "nuts_codes", "x", "y", "geo_status")}
    return hashlib.sha256(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()


def merge(records):
    """De-duplicate by source id, union signal types."""
    out = {}
    for r in records:
        k = (r["source_system"], r["source_record_id"])
        if k in out:
            out[k]["signal_types"] = sorted(set(out[k]["signal_types"]) | set(r["signal_types"]))
        else:
            out[k] = r
    for r in out.values():
        r["content_hash"] = content_hash(r)
    return list(out.values())
