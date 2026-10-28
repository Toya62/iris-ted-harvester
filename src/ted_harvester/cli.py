from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

from .client import TedClient
from .config import Settings
from .geo import NutsGazetteer
from .pipeline import run
from .store import MemoryStore, PostgresStore


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ted-harvester", description="IRIS-SIG-50 TED harvester")
    ap.add_argument("--since", type=date.fromisoformat, help="first publication date; default DB watermark minus overlap")
    ap.add_argument("--until", type=date.fromisoformat, help="last publication date (default today)")
    ap.add_argument("--dry-run", action="store_true", help="no database; write JSONL/report only")
    ap.add_argument("--init-db", action="store_true", help="apply sql/001_signal_ingest.sql first")
    ap.add_argument("--countries", help="comma list of ISO alpha-3 codes or ALL")
    ap.add_argument("--limit", type=int, help="cap number of records (demo)")
    ap.add_argument("--out", default="out", help="output directory")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(levelname)s %(message)s")
    settings = Settings.from_env()
    if a.countries:
        c = () if a.countries.upper() == "ALL" else tuple(x.strip().upper() for x in a.countries.split(","))
        settings = Settings(**{**settings.__dict__, "countries": c})
    if a.dry_run:
        store = MemoryStore()
    else:
        if not settings.database_url:
            print("DATABASE_URL is not set (use --dry-run to run without a database)", file=sys.stderr)
            return 2
        store = PostgresStore(settings.database_url)
        if a.init_db:
            store.ensure_schema()
    gaz = NutsGazetteer.from_csv(settings.nuts_centroids)
    if not gaz.rows:
        logging.warning("NUTS centroid table %s missing/empty: all locations will be unresolved", settings.nuts_centroids)
    records, rep = run(settings, TedClient(settings), store, gaz, a.since, a.until, a.limit)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "records.jsonl").open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps({k: v for k, v in r.items() if k != "raw_payload"}, ensure_ascii=False, default=str) + "\n")
    (out / "report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(rep, indent=2, ensure_ascii=False))
    return 1 if rep["category_errors"] else 0
