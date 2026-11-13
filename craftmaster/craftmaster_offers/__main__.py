"""Command line: ``python -m craftmaster_offers evaluate | case <id> | quote <company> [file]``."""

from __future__ import annotations

import argparse
import sys

from .data import load
from .evaluate import offer_for_case, report
from .language import parse_measurements, render_offer
from .pricing import PriceBook
from .quote import build_offer


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="craftmaster_offers")
    parser.add_argument("--workbook", help="Pfad zur Excel-Datei (sonst CRAFTMASTER_WORKBOOK oder data/)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("evaluate", help="Engine gegen die Musterlösungen prüfen")
    case = sub.add_parser("case", help="Angebot für einen Fall aus der Excel erstellen")
    case.add_argument("case_id")
    case.add_argument("--neu", action="store_true", help="vorhandene Angebotsversionen ignorieren, nur Aufmaß verwenden")
    quote = sub.add_parser("quote", help="Angebot aus einem frei eingegebenen Aufmaß erstellen")
    quote.add_argument("company", help="Firmenname oder ein eindeutiger Teil davon")
    quote.add_argument("file", nargs="?", help="Textdatei mit einer Aufmaßzeile pro Position (sonst Standardeingabe)")
    args = parser.parse_args(argv)

    ds = load(args.workbook)
    if args.command == "evaluate":
        text, ok = report(ds)
        print(text)
        return 0 if ok else 1

    if args.command == "case":
        if args.case_id not in ds.cases():
            print(f"Unbekannter Fall. Verfügbar: {', '.join(ds.cases())}", file=sys.stderr)
            return 2
        offer = offer_for_case(ds, args.case_id, use_existing_draft=not args.neu)
        project = ds.rows("Project context", args.case_id)[0]["Project"]
        print(render_offer(offer, ds.company_of[args.case_id], project))
        return 0

    companies = sorted(set(ds.company_of.values()))
    matches = [c for c in companies if args.company.casefold() in c.casefold()]
    if len(matches) != 1:
        print(f"Firma nicht eindeutig. Verfügbar: {'; '.join(companies)}", file=sys.stderr)
        return 2
    text = open(args.file, encoding="utf-8").read() if args.file else sys.stdin.read()
    measurements, unread = parse_measurements(text)
    offer = build_offer(measurements, PriceBook(ds.services(matches[0]), ds.past_lines(matches[0])))
    offer.questions += [f"Zeile nicht lesbar: „{line}“" for line in unread]
    print(render_offer(offer, matches[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
