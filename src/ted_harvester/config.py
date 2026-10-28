"""Configuration and query definitions for the TED infrastructure harvester."""

import os
from datetime import date
from typing import Dict, List, Optional

DEFAULT_API_URL = "https://api.ted.europa.eu/v3/notices/search"
API_URL = os.environ.get("TED_API_URL", DEFAULT_API_URL)

SOURCE_SYSTEM = "ted"

# Essential fields requested from TED Search API v3
NOTICE_FIELDS: List[str] = [
    "publication-number",
    "notice-title",
    "publication-date",
    "place-of-performance",
    "buyer-country",
    "links",
]
FIELDS = NOTICE_FIELDS


def queries(since: date, until: Optional[date] = None) -> Dict[str, str]:
    """
    Build TED API v3 query expressions for each required infrastructure domain:
      - grid_cabling: CPV 3132* (power cables) or 45231400 (laying of electricity power lines)
      - transformers: CPV 3117* (power transformers)
      - public_data_centre: Full-text match on data centre / Rechenzentrum terms
    """
    date_clause = f"publication-date>={since:%Y%m%d}"
    if until:
        date_clause += f" AND publication-date<={until:%Y%m%d}"

    return {
        "grid_cabling": f"(classification-cpv=3132* OR classification-cpv=45231400) AND {date_clause}",
        "transformers": f"classification-cpv=3117* AND {date_clause}",
        "public_data_centre": f'FT~("data centre" OR "data center" OR "Rechenzentrum") AND {date_clause}',
    }
