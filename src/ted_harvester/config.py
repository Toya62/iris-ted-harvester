import os
from datetime import date

API_URL = os.environ.get("TED_API_URL", "https://api.ted.europa.eu/v3/notices/search")
SOURCE_SYSTEM = "ted"
FIELDS = ["publication-number", "notice-title", "publication-date", "place-of-performance", "buyer-country", "links"]


def queries(since: date, until: date | None = None) -> dict[str, str]:
    rng = f"publication-date>={since:%Y%m%d}"
    if until:
        rng += f" AND publication-date<={until:%Y%m%d}"
    return {
        "grid_cabling": f"(classification-cpv=3132* OR classification-cpv=45231400) AND {rng}",
        "transformers": f"classification-cpv=3117* AND {rng}",
        "public_data_centre": f'FT~("data centre" OR "data center" OR "Rechenzentrum") AND {rng}',
    }
