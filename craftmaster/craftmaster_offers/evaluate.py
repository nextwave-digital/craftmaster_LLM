"""Check the engine against the workbook: issued offers and the review sheets."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .data import Dataset, dec
from .pricing import PriceBook, round_cents
from .quote import OfferDraft, build_offer

QUOTATION_REQUEST = "Prepare a quotation"


def cents(value) -> int:
    return round_cents(dec(value) * 100)


def current_draft_prices(ds: Dataset, case_id: str) -> dict[str, int]:
    """Unit prices of the latest offer version, keyed by measurement id."""
    offers = ds.offers(case_id)
    if not offers:
        return {}
    return {
        line["Source measurement id"]: int(line["Unit price (cents)"])
        for line in ds.offer_lines(offers[-1]["Source ID"])
        if line["Source measurement id"] and line["Unit price (cents)"] is not None
    }


def offer_for_case(ds: Dataset, case_id: str, use_existing_draft: bool = True) -> OfferDraft:
    company = ds.company_of[case_id]
    prices = PriceBook(ds.services(company), ds.past_lines(company, exclude_case=case_id))
    draft = current_draft_prices(ds, case_id) if use_existing_draft else None
    return build_offer(ds.measurements(case_id), prices, draft)


@dataclass
class Check:
    case_id: str
    ok: bool
    detail: str


def check_first_offers(ds: Dataset) -> list[Check]:
    """Measurements + catalog only: does the result equal the first offer that was actually issued?"""
    results = []
    for case_id in ds.cases():
        offers = ds.offers(case_id)
        if not offers:
            continue
        first = offers[0]
        real = ds.offer_lines(first["Source ID"])
        mine = offer_for_case(ds, case_id, use_existing_draft=False)
        real_by_measurement = {line["Source measurement id"]: line for line in real}
        wrong = len(real) - len(mine.lines) if len(real) != len(mine.lines) else 0
        for line in mine.lines:
            ref = real_by_measurement.get(line.measurement_id)
            if (
                ref is None
                or int(ref["Unit price (cents)"]) != line.unit_price_cents
                or int(ref["Source total (cents)"]) != line.net_cents
                or ref["Description"] != line.description
            ):
                wrong += 1
        ok = (
            not wrong
            and not mine.questions
            and mine.net_cents == int(first["Subtotal (cents)"])
            and mine.gross_cents == int(first["Source total (cents)"])
        )
        results.append(Check(case_id, ok, f"{len(mine.lines)}/{len(real)} Positionen, netto {mine.net_cents / 100:.2f} "
                                          f"(Original {int(first['Subtotal (cents)']) / 100:.2f}), Abweichungen {abs(wrong)}"))
    return results


def check_review_answers(ds: Dataset) -> list[Check]:
    """Quotation tasks: action, totals and every position against the review sheets."""
    results = []
    index = {r["Case ID"]: r for r in ds.tables["Case index"]}
    for answer in ds.tables["Review answers"]:
        case_id = answer["Case ID"]
        if not index[case_id]["User request"].startswith(QUOTATION_REQUEST):
            continue
        mine = offer_for_case(ds, case_id)
        problems = []
        if mine.action != answer["Expected action"]:
            problems.append(f"Aktion {mine.action!r} statt {answer['Expected action']!r}")
        for label, got in (("net", mine.net_cents), ("VAT", mine.vat_cents), ("gross", mine.gross_cents)):
            want = cents(answer[f"Expected {label} (EUR)"])
            if got != want:
                problems.append(f"{label} {got / 100:.2f} statt {want / 100:.2f}")
        expected_lines = ds.rows("Review positions", case_id)
        if len(expected_lines) != len(mine.lines):
            problems.append(f"{len(mine.lines)} statt {len(expected_lines)} Positionen")
        for want, got in zip(sorted(expected_lines, key=lambda r: int(r["Line"])), mine.lines):
            if (
                want["Description"] != got.description
                or dec(want["Quantity"]) != got.quantity
                or cents(want["Unit price (EUR)"]) != got.unit_price_cents
                or cents(want["Expected net (EUR)"]) != got.net_cents
            ):
                problems.append(f"Position {want['Line']} weicht ab")
        if mine.action == "clarification" and not mine.questions:
            problems.append("keine Rückfrage gestellt")
        detail = "; ".join(problems) or f"{mine.action}, {len(mine.lines)} Positionen, netto {mine.net_cents / 100:.2f}"
        results.append(Check(case_id, not problems, detail))
    return results


@dataclass
class HistoryResult:
    case_id: str
    positions: int
    priced: int
    priced_real_cents: int
    priced_mine_cents: int

    @property
    def deviation(self) -> Decimal | None:
        if not self.priced_real_cents:
            return None
        return Decimal(self.priced_mine_cents - self.priced_real_cents) / self.priced_real_cents


def check_history_only(ds: Dataset) -> list[HistoryResult]:
    """No catalog at all: price each position from the company's other projects and compare with the issued offer."""
    results = []
    for case_id in ds.cases():
        offers = ds.offers(case_id)
        if not offers:
            continue
        real = {line["Source measurement id"]: line for line in ds.offer_lines(offers[0]["Source ID"])}
        company = ds.company_of[case_id]
        mine = build_offer(ds.measurements(case_id), PriceBook([], ds.past_lines(company, exclude_case=case_id)))
        matched = [(line, real[line.measurement_id]) for line in mine.lines if line.measurement_id in real]
        results.append(
            HistoryResult(
                case_id=case_id,
                positions=len(real),
                priced=len(matched),
                priced_real_cents=sum(int(ref["Source total (cents)"]) for _, ref in matched),
                priced_mine_cents=sum(line.net_cents for line, _ in matched),
            )
        )
    return results


def report(ds: Dataset) -> tuple[str, bool]:
    out = []
    first = check_first_offers(ds)
    review = check_review_answers(ds)
    history = check_history_only(ds)

    def block(title, checks):
        passed = sum(c.ok for c in checks)
        out.append(f"{title}: {passed}/{len(checks)} Fälle stimmen")
        for c in checks:
            out.append(f"  {'OK ' if c.ok else 'ABW'} {c.case_id:<22} {c.detail}")
        out.append("")

    block("A  Nur Aufmaß + Katalog gegen das erste tatsächlich abgegebene Angebot", first)
    block("B  Angebotsaufgaben gegen die Musterlösung (Review answers / Review positions)", review)

    positions = sum(h.positions for h in history)
    priced = sum(h.priced for h in history)
    real = sum(h.priced_real_cents for h in history)
    mine = sum(h.priced_mine_cents for h in history)
    out.append("C  Ohne Katalog, Preise nur aus anderen Projekten derselben Firma")
    out.append(f"  bepreist: {priced}/{positions} Positionen ({priced / positions:.0%})")
    if real:
        out.append(f"  Abweichung der bepreisten Summe zum Originalangebot: {(mine - real) / real:+.2%}")
    for h in history:
        dev = "–" if h.deviation is None else f"{h.deviation:+.2%}"
        out.append(f"  {h.case_id:<22} {h.priced:>2}/{h.positions} Positionen, Abweichung {dev}")
    return "\n".join(out), all(c.ok for c in first + review)
