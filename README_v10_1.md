# PRISMA v10.1

## Schwerpunkt

PRISMA v10.1 baut auf dem Grabber-TXT-Import auf und ergänzt eine Corpus-Auswertung für ZIP-Dateien mit vielen anonymisierten Pflegeplänen.

## Grundsätze

- Grabber `.txt` ist der Standardimport.
- Unbekannte Leistungen sind keine Fehler, sondern Review-Einträge.
- Es gibt keine automatischen Fuzzy- oder Ähnlichkeitsmatches.
- Ähnlich klingende Leistungen werden nicht automatisch zusammengeführt.
- Zuordnungen laufen nur über exakte, verifizierte oder manuell freigegebene Alias-/LEP-Zuordnungen.

## Start

```powershell
python -m streamlit run prisma_app_v10_1.py
```

## Neue Funktionen

### Einzelplan

- Analyse einer einzelnen Grabber-TXT-Datei
- Parser-Ausgabe
- Matches
- Review-Liste unbekannter Leistungen
- Regelbefunde
- Statistik

### Corpus-Analyse

- ZIP-Upload mit mehreren Grabber-TXT-Dateien
- Auswertung nach Datei, Station und Fachabteilung
- häufigste Pakete
- häufigste Leistungen
- häufigste unbekannte Leistungen
- Parser-Warnungen
- Export aller Corpus-Auswertungen als ZIP

## Wichtige Dateien

- `prisma_app_v10_1.py` - Streamlit-App
- `prisma_parser_v10_1.py` - Grabber-TXT-Parser
- `engine/` - Matching und Regel-Engine
- `data/lep_aliases_v10_1.json` - Aliasbasis
- `data/lep_rules_v10_1.json` - LEP-/lokale Regelbasis
- `data/entry_classification_v10_1.json` - Klassifikation von Paketen und Einträgen
