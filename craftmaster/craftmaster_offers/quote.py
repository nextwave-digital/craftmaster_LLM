"""Turn confirmed measurements into an offer draft, or into the questions that block one."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .data import Measurement
from .pricing import PriceBook, normalize_unit, round_cents

UNCONFIRMED_UNITS = {"", "ungeklärt", "unklar", "?"}


@dataclass(frozen=True)
class OfferLine:
    position: int
    description: str
    quantity: Decimal
    unit: str
    unit_price_cents: int
    tax_rate: Decimal
    net_cents: int
    price_source: str  # "draft" | "catalog" | "history"
    measurement_id: str | None = None
    service_id: str | None = None


@dataclass
class OfferDraft:
    lines: list[OfferLine] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def action(self) -> str:
        return "quotation draft" if self.lines else "clarification"

    @property
    def net_cents(self) -> int:
        return sum(line.net_cents for line in self.lines)

    @property
    def vat_cents(self) -> int:
        by_rate: dict[Decimal, int] = {}
        for line in self.lines:
            by_rate[line.tax_rate] = by_rate.get(line.tax_rate, 0) + line.net_cents
        return sum(round_cents(Decimal(net) * rate / 100) for rate, net in by_rate.items())

    @property
    def gross_cents(self) -> int:
        return self.net_cents + self.vat_cents


def build_offer(
    measurements: list[Measurement],
    prices: PriceBook,
    draft_prices: dict[str, int] | None = None,
    default_tax_rate: Decimal = Decimal(19),
) -> OfferDraft:
    """Price each measurement.

    ``draft_prices`` maps measurement id -> unit price of the project's current
    offer version. Those prices were set or negotiated by a person, so they win
    over the list price. Older, superseded versions must not be passed in.
    """
    draft_prices = draft_prices or {}
    offer = OfferDraft()
    if not measurements:
        offer.questions.append("Es liegt kein Aufmaß vor. Bitte Maße und Leistungsumfang bestätigen.")
        return offer

    for m in measurements:
        unit = normalize_unit(m.unit)
        if unit.casefold() in UNCONFIRMED_UNITS:
            offer.questions.append(
                f"„{m.name}“: Die Einheit zur Menge {m.quantity} ist nicht bestätigt. "
                "Bitte Maße, Einheit und Ausführungsbedingungen klären."
            )
            continue
        if m.quantity <= 0:
            offer.questions.append(f"„{m.name}“: Die Menge {m.quantity} {unit} ist nicht plausibel. Bitte prüfen.")
            continue

        service, score = prices.find_service(m.name)
        history = prices.history(m.name, unit)
        description = service.title if service else m.name
        tax_rate = service.tax_rate if service else default_tax_rate

        if service and normalize_unit(service.unit) != unit:
            offer.questions.append(
                f"„{m.name}“: Aufmaß in {unit}, Katalogleistung „{service.title}“ wird in {service.unit} abgerechnet. "
                "Ohne bestätigte Umrechnung wird keine Position angelegt."
            )
            continue
        if service and not service.active:
            offer.questions.append(f"„{service.title}“ ist im Katalog inaktiv. Bitte vor Verwendung freigeben.")
            continue

        if m.id in draft_prices:
            price, source = draft_prices[m.id], "draft"
            if service and service.price_cents is not None and service.price_cents != price:
                offer.notes.append(
                    f"Pos. „{description}“: Entwurfspreis {price / 100:.2f} € beibehalten "
                    f"(Listenpreis {service.price_cents / 100:.2f} €)."
                )
        elif service and service.price_cents is not None:
            price, source = service.price_cents, "catalog"
        elif history:
            price, source = history.median_cents, "history"
            offer.notes.append(
                f"Pos. „{description}“: kein Listenpreis; Preis {price / 100:.2f} € ist der Median aus "
                f"{history.observations} früheren Positionen in {history.projects} Projekten "
                f"({history.low_cents / 100:.2f}–{history.high_cents / 100:.2f} €). Bitte bestätigen."
            )
        else:
            reason = "hat keinen Verkaufspreis" if service else "ist weder im Katalog noch in früheren Angeboten zu finden"
            offer.questions.append(f"„{m.name}“ {reason}. Bitte Leistung und Verkaufspreis angeben.")
            continue

        if service and score < 1.0:
            offer.notes.append(f"„{m.name}“ wurde der Katalogleistung „{service.title}“ zugeordnet (Ähnlichkeit {score:.0%}).")

        offer.lines.append(
            OfferLine(
                position=len(offer.lines) + 1,
                description=description,
                quantity=m.quantity,
                unit=unit,
                unit_price_cents=price,
                tax_rate=tax_rate,
                net_cents=round_cents(m.quantity * price),
                price_source=source,
                measurement_id=m.id,
                service_id=service.id if service else None,
            )
        )
    return offer
