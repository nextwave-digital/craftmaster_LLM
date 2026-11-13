"""The language edge: human text <-> structured data.

This is the only place a language model belongs in the offer flow:

* inbound  - turn what a person wrote or said into ``Measurement`` records
* outbound - turn an ``OfferDraft`` into readable text

Both directions are implemented here with plain rules so the pipeline runs and
can be tested without any model. A model replaces ``parse_measurements`` for
free-form input and may reword ``render_offer``; it never produces a number.
"""

from __future__ import annotations

import re
from decimal import Decimal

from .data import Measurement
from .pricing import normalize_unit
from .quote import OfferDraft

_NUM = r"(?P<qty>\d{1,3}(?:\.\d{3})+,\d+|\d+(?:[.,]\d+)?)"
_UNIT = r"(?P<unit>m²|m2|qm|m³|m3|cbm|lfdm|lfm|Stück|Stk\.?|Std\.?|Stunden|kg|m|l|h)(?![\w²³])"
_QTY_FIRST = re.compile(rf"^{_NUM}\s*(?:{_UNIT}\s+)?(?P<name>.+)$", re.IGNORECASE)
_QTY_LAST = re.compile(rf"^(?P<name>.+?)\s*[:;,]?\s+{_NUM}\s*(?:{_UNIT})?$", re.IGNORECASE)


def _number(text: str) -> Decimal:
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    return Decimal(text)


def parse_measurements(text: str) -> tuple[list[Measurement], list[str]]:
    """Read one measurement per line, e.g. ``111,069 m Rohrtrasse aufnehmen – Standard``.

    Returns the measurements and the lines that could not be read. A quantity
    without a recognisable unit is kept with unit ``ungeklärt`` so the engine asks.
    """
    found, unread = [], []
    for raw in text.splitlines():
        line = raw.strip().lstrip("-*• ").strip()
        if not line or line.startswith("#"):
            continue
        match = _QTY_FIRST.match(line) or _QTY_LAST.match(line)
        if not match:
            unread.append(raw.strip())
            continue
        unit = normalize_unit(match.group("unit")) if match.group("unit") else "ungeklärt"
        found.append(Measurement(name=match.group("name").strip(" :;,"), quantity=_number(match.group("qty")), unit=unit))
    return found, unread


def euro(cents: int) -> str:
    text = f"{cents / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} €"


def _qty(value: Decimal) -> str:
    return f"{value.normalize():f}".replace(".", ",")


def render_offer(offer: OfferDraft, company: str = "", project: str = "") -> str:
    """German plain-text version of an offer draft or of the open questions."""
    out = []
    title = "Angebotsentwurf" if offer.lines else "Rückfragen vor Angebotserstellung"
    out.append(" – ".join(part for part in (title, company, project) if part))
    out.append("")
    if offer.lines:
        width = max(len(line.description) for line in offer.lines)
        for line in offer.lines:
            out.append(
                f"{line.position:>3}  {line.description:<{width}}  {_qty(line.quantity):>10} {line.unit:<4} "
                f"× {euro(line.unit_price_cents):>12} = {euro(line.net_cents):>14}"
            )
        out += [
            "",
            f"Netto:  {euro(offer.net_cents):>14}",
            f"MwSt.:  {euro(offer.vat_cents):>14}",
            f"Brutto: {euro(offer.gross_cents):>14}",
        ]
    if offer.questions:
        out += ["", "Offene Fragen:"] + [f"  - {q}" for q in offer.questions]
    if offer.notes:
        out += ["", "Hinweise:"] + [f"  - {n}" for n in offer.notes]
    return "\n".join(out)
