# Project PRISMA

PRISMA ist ein gezieltes Copy-Paste-Werkzeug für die fachliche Kontrolle
ausgewählter Pflegeleistungen. Es ersetzt keine pflegefachliche Bewertung und
analysiert nicht automatisch einen vollständigen Pflegeplan.

## Aktueller Schwerpunkt

Der Branch `feature/targeted-service-check` führt einen bewusst kleinen
Arbeitsablauf ein:

1. Auffällige Leistungen aus SAP kopieren.
2. Eine Leistung pro Zeile in PRISMA einfügen.
3. Titel ausschließlich exakt oder über bestätigte Aliase erkennen.
4. Nur bestätigte Beziehungen zwischen den eingefügten Leistungen anzeigen.

Beispiel:

```text
In Rollstuhl mobilisieren PV_4XTGL4 Aktiv
In das Bett mobilisieren PV_3XTGL5 Aktiv
Beim Gehen begleiten P_EINMAL Aktiv
An Bettrand mobilisieren PV_3XTGL2 Aktiv
```

Zykluscodes und Status dürfen mitkopiert werden. Reine Leistungstitel
funktionieren ebenfalls.

## Ausgaben

- **Bereits eingeschlossen:** Eine eingefügte Leistung ist laut bestätigter
  Regel in einer anderen eingefügten Leistung enthalten.
- **Nicht eingeschlossen – separat prüfen:** Beide Leistungen wurden eingefügt,
  die Regelmatrix weist aber ausdrücklich aus, dass eine die andere nicht
  enthält.
- **Erkannt, aber ohne Regelbefund:** Die Leistung ist bekannt, zwischen den
  ausgewählten Einträgen besteht jedoch keine bestätigte Beziehung.
- **Keine exakte Zuordnung:** Der Eintrag bleibt bewusst ungeklärt.

PRISMA schlägt keine fehlenden Leistungen vor, bewertet keine medizinische
Notwendigkeit und verwendet keine automatischen Fuzzy- oder
Ähnlichkeitsmatches.

## Installation und Start

Voraussetzung ist Python 3.10 oder neuer.

```powershell
py -V:3.14 -m pip install -r requirements.txt
py -V:3.14 -m streamlit run app.py
```

Eine virtuelle Umgebung ist optional.

## Tests

```powershell
py -V:3.14 -m unittest discover -s tests -v
```

Die bisherige vollständige Grabber-TXT- und Corpus-Analyse bleibt über die
Git-Historie und unter `archive/` nachvollziehbar. Die neue Produktrichtung
konzentriert sich auf den gezielten Leistungsabgleich im Audit.
