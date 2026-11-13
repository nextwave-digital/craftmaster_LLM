# Craftmaster Angebots-Engine

Aus einem Aufmaß entsteht ein Angebotsentwurf. Alle Zahlen werden nachgeschlagen und gerechnet; ein Sprachmodell
wird nur an den Rändern gebraucht (Text → Aufmaß, Angebot → Text) und erzeugt nie selbst einen Preis.

Dieses Verzeichnis ist unabhängig vom restlichen Repository (Lehrcode „LLMs from Scratch“).

## Ablauf

1. **Aufmaß einlesen** (`language.py`): eine Zeile pro Position, z. B. `111,069 m Rohrtrasse aufnehmen – Standard`.
2. **Leistung zuordnen** (`pricing.py`): Name gegen den Leistungskatalog der Firma, exakt oder mit Ähnlichkeit ab 85 %.
3. **Preis bestimmen** (`quote.py`), in dieser Reihenfolge:
   - Preis aus der aktuellen Angebotsversion des Projekts (verhandelte Preise bleiben erhalten),
   - Listenpreis aus dem Katalog,
   - Median aus früheren Angeboten und Auftragsbestätigungen derselben Firma, als Hinweis gekennzeichnet.
4. **Rückfrage statt Position**, wenn die Einheit unbestätigt ist, Aufmaß- und Katalogeinheit nicht zusammenpassen,
   die Leistung inaktiv ist oder kein Verkaufspreis vorliegt.
5. **Summen**: Position = Menge × Einzelpreis, kaufmännisch auf Cent gerundet; MwSt. auf die Nettosumme je Steuersatz.

## Benutzen

Die Excel-Datei liegt unter `data/Craftmaster_Assistant_Cases_EN.xlsx` (nicht versioniert) oder wird über
`--workbook` bzw. `CRAFTMASTER_WORKBOOK` angegeben.

```bash
pip install -r requirements.txt
python -m craftmaster_offers evaluate                    # gegen die Musterlösungen prüfen
python -m craftmaster_offers case feldstrom-REF-005      # Fall aus der Excel
python -m craftmaster_offers case feldstrom-REF-005 --neu  # nur Aufmaß, vorhandene Angebote ignorieren
python -m craftmaster_offers quote feldstrom aufmass.txt # frei eingegebenes Aufmaß
python -m pytest
```

## Stand der Prüfung

- Nur Aufmaß + Katalog ergibt in 15 von 15 Fällen exakt das erste tatsächlich abgegebene Angebot.
- Die 10 Angebotsaufgaben (Rückfrage bzw. Angebotsrevision) stimmen mit „Review answers“ und „Review positions“ überein.
- Ohne Katalog, nur aus den anderen Projekten derselben Firma: 73 % der Positionen bepreisbar, Summe +1,0 % zum Original.

## Noch nicht enthalten

- Sprachmodell für frei formulierte Anfragen; bisher lesen feste Regeln das Aufmaß.
- Rückfragen zu Materialartikeln (fehlender Verkaufs- oder Einkaufspreis, inaktive Artikel).
- Regie-Rechnungen und Schlussrechnungen (Falltypen 012 und 017).
- Einlesen des CSV-Pakets mit 2.000 Projekten.
