from __future__ import annotations

import logging
from collections import Counter
from datetime import date, timedelta

from .client import TedApiError
from .domain import CATEGORIES, build_query
from .normalize import RejectedRecord, normalize

log = logging.getLogger(__name__)


def windows(since: date, until: date, days: int):
    cur = since
    while cur <= until:
        end = min(cur + timedelta(days=days - 1), until)
        yield cur, end
        cur = end + timedelta(days=1)


def run(settings, client, store, gaz, since=None, until=None, limit=None):
    until = until or date.today()
    if since is None:
        wm = store.watermark()
        since = (wm - timedelta(days=settings.overlap_days)) if wm else until - timedelta(days=settings.default_lookback_days)
    rep = {"start": since.isoformat(), "end": until.isoformat(), "countries": list(settings.countries),
           "fetched_raw": 0, "duplicates_collapsed": 0, "rejected": Counter(), "quality": Counter(),
           "issues": Counter(), "location": Counter(), "categories": Counter(), "load": Counter(),
           "category_errors": {}, "empty_windows": 0}
    found: dict[str, tuple[dict, set]] = {}
    for a, b in windows(since, until, settings.window_days):
        got = 0
        for cat in CATEGORIES:
            try:
                for n in client.search(build_query(cat, a.strftime("%Y%m%d"), b.strftime("%Y%m%d"), settings.countries)):
                    got += 1
                    rep["fetched_raw"] += 1
                    pid = n.get("publication-number") if isinstance(n, dict) else None
                    key = pid.strip() if isinstance(pid, str) and pid.strip() else None
                    if key is None:
                        rep["rejected"]["missing_publication_number"] += 1
                        store.reject("missing_publication_number", n)
                        continue
                    if key in found:
                        rep["duplicates_collapsed"] += 1
                        found[key][1].add(cat.name)
                    else:
                        found[key] = (n, {cat.name})
                    found[key] = (n, found[key][1])
            except TedApiError as exc:
                rep["category_errors"][f"{cat.name}:{a}..{b}"] = str(exc)
                log.error("category %s window %s..%s failed: %s", cat.name, a, b, exc)
        if got == 0 and not rep["category_errors"]:
            rep["empty_windows"] += 1
    records = []
    for key, (n, cats) in sorted(found.items()):
        if limit is not None and len(records) >= limit:
            break
        try:
            r = normalize(n, sorted(cats), gaz)
        except RejectedRecord as exc:
            rep["rejected"][str(exc)] += 1
            store.reject(str(exc), n)
            continue
        rep["quality"][r["quality_status"]] += 1
        rep["location"][r["location_status"]] += 1
        for c in r["signal_categories"]:
            rep["categories"][c] += 1
        for i in r["quality_issues"]:
            rep["issues"][i] += 1
        if r["quality_status"] == "invalid":
            rep["rejected"]["invalid_quality:" + ",".join(r["quality_issues"])] += 1
            store.reject("invalid_quality", n)
            continue
        records.append(r)
    rep["load"].update(store.upsert(records))
    return records, {k: (dict(v) if isinstance(v, Counter) else v) for k, v in rep.items()}
