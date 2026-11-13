from decimal import Decimal

import pytest

from craftmaster_offers.data import Measurement, PastLine, Service, load, workbook_path
from craftmaster_offers.evaluate import check_first_offers, check_review_answers
from craftmaster_offers.language import parse_measurements, render_offer
from craftmaster_offers.pricing import PriceBook
from craftmaster_offers.quote import build_offer


def service(title, unit, price, active=True):
    return Service(id=title, company="Test", code="T", title=title, unit=unit, price_cents=price, tax_rate=Decimal(19), active=active)


CATALOG = [
    service("Rohrtrasse aufnehmen – Standard", "m", 395),
    service("Wand verputzen – Bestand", "m²", None),
    service("Altanstrich entfernen", "m²", 900, active=False),
]


def test_catalog_price_rounding_and_vat():
    offer = build_offer([Measurement("Abschnitt 1: Rohrtrasse aufnehmen – Standard", Decimal("111.069"), "m")], PriceBook(CATALOG))
    assert offer.action == "quotation draft"
    assert offer.lines[0].net_cents == 43872  # 111.069 × 3.95 = 438.72255
    assert (offer.net_cents, offer.vat_cents, offer.gross_cents) == (43872, 8336, 52208)


def test_half_cents_round_up():
    offer = build_offer([Measurement("Rohrtrasse aufnehmen – Standard", Decimal("0.5"), "m")], PriceBook([service("Rohrtrasse aufnehmen – Standard", "m", 1)]))
    assert offer.lines[0].net_cents == 1


def test_unconfirmed_unit_asks_instead_of_quoting():
    offer = build_offer([Measurement("Kundenangabe 10, Einheit nicht bestätigt", Decimal(10), "ungeklärt")], PriceBook(CATALOG))
    assert offer.action == "clarification"
    assert offer.net_cents == 0 and len(offer.questions) == 1


def test_unit_mismatch_inactive_and_unknown_are_questions():
    offer = build_offer(
        [
            Measurement("Rohrtrasse aufnehmen – Standard", Decimal(5), "m²"),
            Measurement("Altanstrich entfernen", Decimal(5), "m²"),
            Measurement("Dach neu eindecken", Decimal(5), "m²"),
        ],
        PriceBook(CATALOG),
    )
    assert not offer.lines and len(offer.questions) == 3


def test_missing_list_price_falls_back_to_history_and_says_so():
    history = [PastLine("Test", f"p{i}", "Wand verputzen – Bestand", "m²", price) for i, price in enumerate((2000, 2100, 2600))]
    offer = build_offer([Measurement("Wand verputzen – Bestand", Decimal(10), "m²")], PriceBook(CATALOG, history))
    assert offer.lines[0].unit_price_cents == 2100 and offer.lines[0].price_source == "history"
    assert any("Median" in note for note in offer.notes)


def test_missing_price_without_history_is_a_question():
    offer = build_offer([Measurement("Wand verputzen – Bestand", Decimal(10), "m²")], PriceBook(CATALOG))
    assert not offer.lines and "Verkaufspreis" in offer.questions[0]


def test_draft_price_wins_over_list_price():
    m = Measurement("Rohrtrasse aufnehmen – Standard", Decimal(10), "m", id="m1")
    offer = build_offer([m], PriceBook(CATALOG), draft_prices={"m1": 403})
    assert offer.lines[0].unit_price_cents == 403 and offer.lines[0].price_source == "draft"


def test_parse_and_render_roundtrip():
    found, unread = parse_measurements(
        "111,069 m Rohrtrasse aufnehmen – Standard\nRohrtrasse aufnehmen - Standard: 1.250,5 lfm\n10 Schmierstoff\nbitte bald"
    )
    assert [(m.quantity, m.unit) for m in found] == [(Decimal("111.069"), "m"), (Decimal("1250.5"), "m"), (Decimal(10), "ungeklärt")]
    assert unread == ["bitte bald"]
    text = render_offer(build_offer(found, PriceBook(CATALOG)))
    assert "438,72 €" in text and "4.939,48 €" in text and "Offene Fragen" in text


needs_workbook = pytest.mark.skipif(not workbook_path().exists(), reason="case workbook not available")


@needs_workbook
def test_measurements_reproduce_first_issued_offers():
    checks = check_first_offers(load())
    assert len(checks) == 15 and all(c.ok for c in checks), [c for c in checks if not c.ok]


@needs_workbook
def test_quotation_tasks_match_review_answers():
    checks = check_review_answers(load())
    assert len(checks) == 10 and all(c.ok for c in checks), [c for c in checks if not c.ok]
