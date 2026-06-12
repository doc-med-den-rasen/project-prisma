# PRISMA v10.2

## Schwerpunkt

v10.2 baut auf v10.1 auf und verbessert vor allem die Corpus-Auswertung.

Neu:

- Grabber-TXT bleibt Standardimport.
- ZIP-/Corpus-Analyse bleibt erhalten.
- Unbekannte Leistungen werden nicht als Fehler gewertet.
- Es gibt weiterhin **keine automatischen Fuzzy- oder Ähnlichkeitsmatches**.
- Unbekannte Einträge werden in eine bessere **Sortier-/Reviewliste** überführt.

## Wichtiges Projektprinzip

Ähnlich klingende Maßnahmen werden nicht automatisch zusammengeführt.

Beispiel:

- `Vitalzeichen messen`
- `Vitalzeichen mit Monitor messen`

Diese Einträge dürfen fachlich unterschiedlich sein und bleiben getrennt, solange keine manuell bestätigte und fachlich korrekte Zuordnung vorliegt.

## Neue Review-Kategorien

Unbekannte Einträge bekommen in v10.2 zusätzliche Sortierspalten:

- Review-Kategorie
- Review-Klasse
- Vermutete Ursache
- Review-Priorität
- Prüffrage
- Manuelle Entscheidung
- Team-Kommentar
- Auto-Match erlaubt = False

Diese Einstufung ist **kein Match** und keine fachliche Gleichsetzung. Sie dient nur dazu, die manuelle Nacharbeit besser zu priorisieren.

## Start

```powershell
python -m streamlit run prisma_app_v10_2.py
```

## Empfohlener Ablauf

1. `Set01.zip` oder `Set02.zip` in der Corpus-Analyse hochladen.
2. Tab `Review: unbekannt` prüfen.
3. Sortierliste als CSV exportieren.
4. Manuelle Entscheidung im Team ergänzen.
5. Daraus später die Klassifikation / Aliasbasis gezielt erweitern.
