"""Command-line interface for the TED infrastructure harvester."""

import argparse
from datetime import date, timedelta
import json
import logging
import os
import sys
from typing import List, Optional

from .geo import load_centroids
from .pipeline import harvest

logger = logging.getLogger("ted_harvester")

__all__ = ["harvest", "main"]


def build_parser() -> argparse.ArgumentParser:
    """Configure command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="ted-harvest",
        description="Harvest EU procurement infrastructure notices into iris_staging.signal_ingest.",
    )
    parser.add_argument(
        "--since",
        type=date.fromisoformat,
        default=date.today() - timedelta(days=7),
        help="Earliest publication date (ISO format YYYY-MM-DD, defaults to 7 days ago)",
    )
    parser.add_argument(
        "--until",
        type=date.fromisoformat,
        default=None,
        help="Latest publication date (ISO format YYYY-MM-DD, optional)",
    )
    parser.add_argument(
        "--max-per-category",
        type=int,
        default=None,
        help="Limit number of notices retrieved per signal category (useful for quick sampling)",
    )
    parser.add_argument(
        "--centroids",
        default="data/nuts3_centroids.csv",
        help="Path to NUTS-3 centroids CSV file (default: data/nuts3_centroids.csv)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run search, normalization, and reporting without connecting to PostgreSQL",
    )
    parser.add_argument(
        "--output",
        default="output/sample.json",
        help="Path to write sample normalized JSON records (default: output/sample.json)",
    )
    parser.add_argument(
        "--report-output",
        default="output/quality_report.json",
        help="Path to write quality report JSON (default: output/quality_report.json)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable detailed debug logging",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI execution routine."""
    parser = build_parser()
    args = parser.parse_args(argv)

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if not os.path.exists(args.centroids):
        logger.warning(
            "Centroids file '%s' not found. Run 'python scripts/build_nuts3_centroids.py' "
            "to generate it. Locations will fall back to 'unresolved'.",
            args.centroids,
        )
        centroids = {}
    else:
        centroids = load_centroids(args.centroids)

    records, report = harvest(
        since=args.since,
        until=args.until,
        centroids=centroids,
        per_category=args.max_per_category,
    )

    # Save sample output records (omitting large raw payload for reviewability)
    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        export_records = [{k: v for k, v in record.items() if k != "raw"} for record in records]
        with open(args.output, mode="w", encoding="utf-8") as handle:
            json.dump(export_records, handle, indent=2, ensure_ascii=False)
        logger.info("Exported %d sample records to %s", len(export_records), args.output)

    # Database ingestion phase
    if not args.dry_run:
        import psycopg
        from .load import upsert

        dsn = os.environ.get("TED_DSN")
        if not dsn:
            logger.error("TED_DSN environment variable not set. Provide TED_DSN or use --dry-run.")
            sys.exit(1)

        try:
            with psycopg.connect(dsn) as conn:
                load_stats = upsert(conn, records)
                report["load"] = load_stats
        except Exception as exc:
            logger.error("Failed to load records into database: %s", exc)
            sys.exit(2)

    # Save quality report
    if args.report_output:
        os.makedirs(os.path.dirname(args.report_output) or ".", exist_ok=True)
        with open(args.report_output, mode="w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, ensure_ascii=False)

    print(json.dumps(report, indent=2))
    return 1 if report["category_errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
