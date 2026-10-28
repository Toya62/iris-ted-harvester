import argparse
import json
import logging
import os
from datetime import date, timedelta

from .geo import load_centroids
from .pipeline import harvest

__all__ = ["harvest", "main"]


def main(argv=None):
    p = argparse.ArgumentParser(description="Harvest TED notices into iris_staging.signal_ingest")
    p.add_argument("--since", type=date.fromisoformat, default=date.today() - timedelta(days=7))
    p.add_argument("--until", type=date.fromisoformat)
    p.add_argument("--max-per-category", type=int, default=None)
    p.add_argument("--centroids", default="data/nuts3_centroids.csv")
    p.add_argument("--dry-run", action="store_true", help="do not touch the database")
    p.add_argument("--output", default="output/sample.json")
    p.add_argument("--report-output", default="output/quality_report.json")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    records, report = harvest(a.since, a.until, load_centroids(a.centroids), a.max_per_category)
    os.makedirs(os.path.dirname(a.output) or ".", exist_ok=True)
    with open(a.output, "w", encoding="utf-8") as f:
        json.dump([{k: v for k, v in r.items() if k != "raw"} for r in records], f, indent=1, ensure_ascii=False)
    if a.report_output:
        os.makedirs(os.path.dirname(a.report_output) or ".", exist_ok=True)
        with open(a.report_output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
    if not a.dry_run:
        import psycopg
        from .load import upsert
        dsn = os.environ.get("TED_DSN")
        if not dsn:
            raise SystemExit("TED_DSN not set (use --dry-run to skip the database)")
        with psycopg.connect(dsn) as conn:
            report["load"] = upsert(conn, records)
            if a.report_output:
                with open(a.report_output, "w", encoding="utf-8") as f:
                    json.dump(report, f, indent=2, ensure_ascii=False)
    print(json.dumps(report, indent=2))
    return 1 if report["category_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
