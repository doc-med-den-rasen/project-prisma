# Project PRISMA

PRISMA analysiert anonymisierte Pflegepläne aus dem Grabber-TXT-Format. Der aktuelle Stand v10.2 bietet Einzel- und Corpus-Auswertungen, exaktes Matching, regelbasierte Hinweise und Review-Listen für unbekannte Leistungen.

## Fachlicher Grundsatz

PRISMA verwendet keine automatischen Fuzzy- oder Ähnlichkeitsmatches. Ähnlich klingende Maßnahmen bleiben getrennt, solange keine fachlich bestätigte Zuordnung vorliegt.

Beispiel:

- `Vitalzeichen messen`
- `Vitalzeichen mit Monitor messen`

Matching ist ausschließlich über exakte Titel, manuell gepflegte Aliase und bestätigte LEP-IDs zulässig. Die Review-Kategorien sortieren unbekannte Einträge nur für die manuelle Prüfung und erzeugen keinen Match.

## Installation

Voraussetzung ist Python 3.10 oder neuer.

```powershell
python -m pip install -r requirements.txt
```

Eine virtuelle Umgebung ist optional. Falls sie genutzt wird, bleibt sie lokal und wird durch `.gitignore` nicht in Git aufgenommen.

## Start

```powershell
python -m streamlit run app.py
```

## Aktive Projektstruktur

```text
app.py                       Streamlit-Oberfläche
parser.py                    Grabber-TXT-Parser
engine/                      Matching, Modelle und Regelprüfung
data/                        Aktive Klassifikation, Aliase und LEP-Regeln
tests/                       Schnelle Regressionstests
samples/                     Platz für anonymisierte Grabber-TXT-Beispiele
docs/PROJECT_STATUS.md       Fachlicher und technischer Projektstand
archive/                     Frühere Versionen und alter XLSX-Pfad
```

Versionsnummern stehen bewusst nicht mehr in den aktiven Dateinamen. Neue Versionen werden in denselben Modulen weiterentwickelt und über Git nachvollzogen, statt parallele Dateikopien anzulegen.

## Tests

```powershell
python -m unittest discover -s tests -v
```

Die Tests sichern insbesondere den Grabber-TXT-Import, eine bekannte Einschlussregel und den Grundsatz ab, dass ähnlich klingende Leistungen nicht automatisch zusammengeführt werden.

## Empfohlener Arbeitsablauf

1. Grabber-TXT oder ZIP mit mehreren Grabber-Dateien laden.
2. Parser- und Match-Ergebnis prüfen.
3. Unbekannte Leistungen als CSV-Reviewliste exportieren.
4. Zuordnungen fachlich und manuell bestätigen.
5. Erst danach Alias-, Klassifikations- oder Regelbasis gezielt erweitern.

Frühere Zwischenstände und der nicht mehr aktive XLSX-Weg liegen nur zur Referenz unter `archive/`. Neue Entwicklung findet ausschließlich in der aktiven Struktur statt.
