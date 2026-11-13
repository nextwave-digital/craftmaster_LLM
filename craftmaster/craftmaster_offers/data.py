"""Load the Craftmaster case workbook into plain Python structures."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import openpyxl

DEFAULT_WORKBOOK = Path(__file__).resolve().parent.parent / "data" / "Craftmaster_Assistant_Cases_EN.xlsx"


def workbook_path(path: str | os.PathLike | None = None) -> Path:
    return Path(path or os.environ.get("CRAFTMASTER_WORKBOOK") or DEFAULT_WORKBOOK)


def dec(value) -> Decimal:
    """Exact decimal from a cell value (floats go through their short repr)."""
    return Decimal(str(value))


@dataclass(frozen=True)
class Service:
    id: str
    company: str
    code: str
    title: str
    unit: str
    price_cents: int | None
    tax_rate: Decimal
    active: bool


@dataclass(frozen=True)
class Measurement:
    name: str
    quantity: Decimal
    unit: str
    id: str | None = None


@dataclass(frozen=True)
class PastLine:
    """One priced position from an earlier offer or order confirmation."""

    company: str
    case_id: str
    description: str
    unit: str
    unit_price_cents: int


@dataclass
class Dataset:
    tables: dict[str, list[dict]]
    company_of: dict[str, str] = field(default_factory=dict)

    def rows(self, sheet: str, case_id: str | None = None) -> list[dict]:
        rows = self.tables.get(sheet, [])
        return rows if case_id is None else [r for r in rows if r["Case ID"] == case_id]

    def cases(self) -> list[str]:
        return [r["Case ID"] for r in self.tables["Project context"]]

    def services(self, company: str) -> list[Service]:
        seen: dict[str, Service] = {}
        for r in self.tables["Services"]:
            if self.company_of[r["Case ID"]] != company:
                continue
            price = r["Price net (cents)"]
            seen[r["Source ID"]] = Service(
                id=r["Source ID"],
                company=company,
                code=r["Internal code"],
                title=r["Title"],
                unit=r["Unit"],
                price_cents=None if price is None else int(price),
                tax_rate=dec(r["Tax rate"]),
                active=bool(r["Is active"]),
            )
        return list(seen.values())

    def measurements(self, case_id: str) -> list[Measurement]:
        return [
            Measurement(name=r["Name"], quantity=dec(r["Measured quantity"]), unit=r["Unit"], id=r["Source ID"])
            for r in self.rows("Measurements", case_id)
        ]

    def offers(self, case_id: str) -> list[dict]:
        return sorted(self.rows("Offers", case_id), key=lambda o: o["Version"])

    def offer_lines(self, offer_id: str) -> list[dict]:
        lines = [r for r in self.tables["Offer lines"] if r["Offer id"] == offer_id]
        return sorted(lines, key=lambda r: int(r["Position number"]))

    def past_lines(self, company: str, exclude_case: str | None = None) -> list[PastLine]:
        out = []
        for sheet in ("Offer lines", "Contract lines"):
            for r in self.tables[sheet]:
                case_id = r["Case ID"]
                if self.company_of[case_id] != company or case_id == exclude_case:
                    continue
                if r["Unit price (cents)"] is None:
                    continue
                out.append(PastLine(company, case_id, r["Description"], r["Unit"], int(r["Unit price (cents)"])))
        return out


def load(path: str | os.PathLike | None = None) -> Dataset:
    wb = openpyxl.load_workbook(workbook_path(path), data_only=True, read_only=True)
    tables: dict[str, list[dict]] = {}
    for ws in wb:
        rows = list(ws.iter_rows(values_only=True))
        # Each sheet has a title block; the table starts at the first row with several filled cells.
        for i, row in enumerate(rows):
            if sum(c is not None for c in row) > 3:
                header = [str(c) for c in row]
                tables[ws.title] = [dict(zip(header, r)) for r in rows[i + 1:] if any(c is not None for c in r)]
                break
    company_of = {r["Case ID"]: r["Company"] for r in tables["Case index"]}
    return Dataset(tables=tables, company_of=company_of)
