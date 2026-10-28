"""Which TED notices count as signals. CPV prefixes are configuration: review with the domain owner.
Public data centres have no dedicated CPV code, so they are matched by full-text terms (false positives expected)."""
from __future__ import annotations

from dataclasses import dataclass

SIGNAL_TYPE = "public_procurement_infrastructure"
COUNTRY_FIELD = "place-of-performance-country-proc"
FIELDS = ("publication-number", "notice-title", "publication-date", "notice-type", "buyer-name", "buyer-country",
          "place-of-performance", "place-of-performance-country-proc", "place-of-performance-city-proc",
          "classification-cpv", "estimated-value-proc", "links")


@dataclass(frozen=True)
class Category:
    name: str
    cpv: tuple[str, ...] = ()
    full_text: tuple[str, ...] = ()

    def expression(self) -> str:
        parts = [f"classification-cpv={c}" for c in self.cpv] + [f'FT~("{t}")' for t in self.full_text]
        return "(" + " OR ".join(parts) + ")"


CATEGORIES = (
    Category("grid_cabling", cpv=("3132*", "45231400")),
    Category("transformers", cpv=("3117*",)),
    Category("public_data_centre", full_text=("data centre", "data center", "Rechenzentrum", "datacenter")),
)


def build_query(cat: Category, start: str, end: str, countries: tuple[str, ...]) -> str:
    """start/end are YYYYMMDD, inclusive."""
    q = f"{cat.expression()} AND publication-date>={start} AND publication-date<={end}"
    if countries:
        q += " AND (" + " OR ".join(f"{COUNTRY_FIELD}={c}" for c in countries) + ")"
    return q
