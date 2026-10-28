from collections import Counter
from datetime import date
from typing import Any

from . import client, config
from .normalize import merge, normalize


def harvest(
    since: date,
    until: date | None,
    centroids: dict[str, tuple[float, float]],
    per_category: int | None = None,
    session=None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Harvest notices across signal categories, normalize, de-duplicate and build quality report."""
    records, issues, errors, raw_count = [], Counter(), {}, 0
    for cat, q in config.queries(since, until).items():
        try:
            for n in client.search(q, session=session, max_records=per_category):
                raw_count += 1
                rec, iss = normalize(n, cat, centroids)
                for i in iss:
                    issues[i] += 1
                if rec:
                    records.append(rec)
        except client.TedError as e:
            errors[cat] = str(e)
    merged = merge(records)
    report = {
        "raw_notices": raw_count,
        "unique_records": len(merged),
        "by_signal_type": dict(Counter(t for r in merged for t in r["signal_types"])),
        "geo": dict(
            Counter(
                r["geo_status"] if r["geo_status"] == "resolved" else f'{r["geo_status"]}: {r["geo_note"]}'
                for r in merged
            )
        ),
        "field_issues": dict(issues),
        "category_errors": errors,
        "load": None,
    }
    return merged, report
