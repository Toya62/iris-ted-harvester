import argparse
import json
import logging
import os
from collections import Counter
from datetime import date, timedelta

from . import client, config
from .geo import load_centroids
from .normalize import merge, normalize


def harvest(since, until, centroids, per_category, session=None):
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
        "raw_notices": raw_count, "unique_records": len(merged),
        "by_signal_type": dict(Counter(t for r in merged for t in r["signal_types"])),
        "geo": dict(Counter(r["geo_status"] if r["geo_status"] == "resolved" else f'{r["geo_status"]}: {r["geo_note"]}' for r in merged)),
        "field_issues": dict(issues), "category_errors": errors, "load": None,
    }
    return merged, report


def main(argv=None):
    p = argparse.ArgumentParser(description="Harvest TED notices into iris_staging.signal_ingest")
    p.add_argument("--since", type=date.fromisoformat, default=date.today() - timedelta(days=7))
    p.add_argument("--until", type=date.fromisoformat)
    p.add_argument("--max-per-category", type=int, default=None)
    p.add_argument("--centroids", default="data/nuts3_centroids.csv")
    p.add_argument("--dry-run", action="store_true", help="do not touch the database")
    p.add_argument("--output", default="output/sample.json")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    records, report = harvest(a.since, a.until, load_centroids(a.centroids), a.max_per_category)
    os.makedirs(os.path.dirname(a.output) or ".", exist_ok=True)
    with open(a.output, "w", encoding="utf-8") as f:
        json.dump([{k: v for k, v in r.items() if k != "raw"} for r in records], f, indent=1, ensure_ascii=False)
    if not a.dry_run:
        import psycopg
        from .load import upsert
        dsn = os.environ.get("TED_DSN")
        if not dsn:
            raise SystemExit("TED_DSN not set (use --dry-run to skip the database)")
        with psycopg.connect(dsn) as conn:
            report["load"] = upsert(conn, records)
    print(json.dumps(report, indent=2))
    return 1 if report["category_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
