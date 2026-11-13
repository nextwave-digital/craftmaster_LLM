"""Where a unit price comes from: service catalog first, then the company's own history."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from difflib import SequenceMatcher

from .data import PastLine, Service

# "Abschnitt 3: Rohrtrasse aufnehmen" -> "Rohrtrasse aufnehmen"
_SECTION_PREFIX = re.compile(r"^\s*(abschnitt|position|pos\.?|raum|bereich)\s*\d+\s*[:.–-]\s*", re.IGNORECASE)
_UNIT_ALIASES = {
    "m2": "m²", "qm": "m²", "m3": "m³", "cbm": "m³", "lfm": "m", "lfdm": "m",
    "stk": "Stk.", "stk.": "Stk.", "stück": "Stk.", "st": "Stk.", "st.": "Stk.",
    "std": "Std.", "std.": "Std.", "h": "Std.", "stunden": "Std.",
}
FUZZY_THRESHOLD = 0.85


def normalize_unit(unit: str | None) -> str:
    unit = (unit or "").strip()
    return _UNIT_ALIASES.get(unit.casefold(), unit)


def normalize_title(text: str) -> str:
    text = _SECTION_PREFIX.sub("", text or "")
    text = re.sub(r"[–—-]", "-", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def round_cents(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class HistoryPrice:
    median_cents: int
    low_cents: int
    high_cents: int
    observations: int
    projects: int


class PriceBook:
    """Catalog and price history of one company."""

    def __init__(self, services: list[Service], past_lines: list[PastLine] = ()):
        self._by_title: dict[str, Service] = {normalize_title(s.title): s for s in services}
        self._history: dict[tuple[str, str], list[PastLine]] = {}
        for line in past_lines:
            key = (normalize_title(line.description), normalize_unit(line.unit))
            self._history.setdefault(key, []).append(line)

    def find_service(self, name: str) -> tuple[Service | None, float]:
        """Best catalog entry for a measurement name and how sure the match is (1.0 = exact)."""
        key = normalize_title(name)
        if key in self._by_title:
            return self._by_title[key], 1.0
        best, score = None, 0.0
        for title, service in self._by_title.items():
            ratio = SequenceMatcher(None, key, title).ratio()
            if ratio > score:
                best, score = service, ratio
        return (best, score) if score >= FUZZY_THRESHOLD else (None, score)

    def history(self, name: str, unit: str) -> HistoryPrice | None:
        lines = self._history.get((normalize_title(name), normalize_unit(unit)))
        if not lines:
            return None
        prices = sorted(line.unit_price_cents for line in lines)
        mid = len(prices) // 2
        median = prices[mid] if len(prices) % 2 else round_cents(Decimal(prices[mid - 1] + prices[mid]) / 2)
        return HistoryPrice(median, prices[0], prices[-1], len(prices), len({line.case_id for line in lines}))
