"""Pipeline orchestration for harvesting and processing TED infrastructure notices."""

from collections import Counter
from datetime import date
import logging
from typing import Any, Dict, List, Optional, Tuple

from . import client, config
from .normalize import merge, normalize

logger = logging.getLogger(__name__)


def harvest(
    since: date,
    until: Optional[date],
    centroids: Dict[str, Tuple[float, float]],
    per_category: Optional[int] = None,
    session: Optional[Any] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Harvest public procurement notices across all target signal domains:
      1. Query each category (grid cabling, transformers, data centres)
      2. Normalize fields and resolve regional geometries
      3. Track field validation issues
      4. Deduplicate notices appearing in multiple searches and merge signal types
      5. Construct concise execution quality report

    Returns:
      (merged_records, quality_report)
    """
    collected_records: List[Dict[str, Any]] = []
    field_issues: Counter = Counter()
    category_errors: Dict[str, str] = {}
    raw_notice_count = 0

    queries = config.queries(since, until)

    for category, query_str in queries.items():
        logger.info("Executing TED search for domain '%s'...", category)
        try:
            category_notice_count = 0
            for raw_notice in client.search(query_str, session=session, max_records=per_category):
                raw_notice_count += 1
                category_notice_count += 1

                normalized_record, issues = normalize(raw_notice, category, centroids)
                for issue in issues:
                    field_issues[issue] += 1

                if normalized_record is not None:
                    collected_records.append(normalized_record)

            logger.info("Retrieved %d raw notices for domain '%s'", category_notice_count, category)

        except client.TedError as exc:
            logger.error("Failed to harvest category '%s': %s", category, exc)
            category_errors[category] = str(exc)

    # De-duplicate across categories (notices matching both transformers & cabling)
    unique_records = merge(collected_records)

    # Compute signal type distribution
    signal_type_counts: Counter = Counter()
    for record in unique_records:
        for stype in record.get("signal_types", []):
            signal_type_counts[stype] += 1

    # Compute geographic resolution status distribution
    geo_distribution: Counter = Counter()
    for record in unique_records:
        status = record.get("geo_status", "unresolved")
        if status == "resolved":
            geo_distribution[status] += 1
        else:
            note = record.get("geo_note", "no details")
            geo_distribution[f"{status}: {note}"] += 1

    quality_report: Dict[str, Any] = {
        "raw_notices": raw_notice_count,
        "unique_records": len(unique_records),
        "by_signal_type": dict(signal_type_counts),
        "geo": dict(geo_distribution),
        "field_issues": dict(field_issues),
        "category_errors": category_errors,
        "load": None,
    }

    return unique_records, quality_report
