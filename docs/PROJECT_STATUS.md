# Project PRISMA – Detaillierte Projektzusammenfassung für Weiterentwicklung

## 1. Projektname

**Project PRISMA**

Langform / Bedeutung:

**Pflegeplan-Regelwerk zur Interventions-, Struktur- und Mapping-Analyse**

PRISMA ist ein lokales Analyse-Tool für anonymisierte Pflegepläne aus dem Krankenhausinformationssystem. Ziel ist es, Pflegeplanungen strukturiert einzulesen, zu analysieren, Leistungen zu klassifizieren, Dubletten und eingeschlossene Leistungen sichtbar zu machen und langfristig die Pflegeplanung gegen den LEP-Katalog sowie hausinterne PPR-2.0-/PMD-Logik prüfbar zu machen.

---

## 2. Fachlicher Hintergrund

Der Anwender arbeitet im Krankenhaus im Bereich Pflegedokumentation. Zu den Aufgaben gehören unter anderem:

* Kontrolle von Patienteneinschätzungen
* Kontrolle von Pflegeplanungen
* Prüfung von PMD-/PPR-2.0-Ausleitungen
* Erkennen von Dopplungen, Fehlplanungen und unklaren Leistungen
* Arbeit mit SAP i.s.h.med als KIS
* Arbeit mit epa als Patienten-Einschätzungssystem
* Arbeit mit LEP als Pflegeleistungskatalog
* Nutzung einer hausinternen PPR-2.0-Mapping-Tabelle

Die Pflegeplanungen enthalten verschiedene Arten von Einträgen:

* offizielle LEP-Leistungen
* PMD-automatisch erzeugte Pakete
* manuell hinzugefügte Pakete
* hausinterne Standards
* QM-/Nachweis-/Compliance-Pakete
* PPR-2.0-Zusatzdaten
* Details / Eigenschaften / Ausprägungen
* strukturell auffällige oder falsch geplante Einträge

---

## 3. Ursprüngliches Ziel

Die ursprüngliche Idee war:

Ein anonymisierter Pflegeplan soll in PRISMA eingelesen werden. PRISMA soll anschließend Hinweise geben wie:

* Diese Leistung ist möglicherweise doppelt geplant.
* Diese Leistung ist bereits in einer anderen Leistung enthalten.
* Diese Leistung ist laut LEP ausgeschlossen und sollte separat geprüft werden.
* Diese Leistung ist unbekannt und muss manuell klassifiziert werden.
* Dieses Paket ist ein hausinterner Standard und nicht wie eine normale LEP-Leistung zu bewerten.
* Dieses Paket ist ein QM-/Nachweis-/PPR-relevanter Marker.

Wichtig: PRISMA soll keine KI-Blackbox sein. Die Logik soll nachvollziehbar, regelbasiert und fachlich prüfbar sein.

---

## 4. Wichtiger Projektgrundsatz: Keine Fuzzy- oder Ähnlichkeitsmatches

Für Project PRISMA gilt dauerhaft:

**Es dürfen keine automatischen Fuzzy-Matches, Ähnlichkeitsmatches oder „klingt ähnlich, also wird es dasselbe sein“-Zuordnungen eingesetzt werden.**

Das ist ein harter fachlicher Grundsatz.

Beispiel:

* `Vitalzeichen messen`
* `Vitalzeichen mit Monitor messen`

Diese beiden Maßnahmen klingen ähnlich, sind aber fachlich unterschiedliche Maßnahmen mit unterschiedlichen Geräten, unterschiedlichen Zeitwerten und anderer Durchführungslogik.

Daher gilt:

* Keine automatische Zusammenführung ähnlicher Titel.
* Keine automatische Gleichsetzung aufgrund ähnlicher Wörter.
* Keine automatische Alias-Erzeugung.
* Unbekannte Leistungen bleiben unbekannt.
* Neue Zuordnungen müssen manuell geprüft und bewusst freigegeben werden.
* Matching darf nur erfolgen über:

  * exakte Titel
  * manuell gepflegte Aliaslisten
  * bestätigte LEP-IDs
  * bewusst definierte lokale Klassifikationen

Corpus-Auswertungen dürfen unbekannte Einträge sortieren und priorisieren, aber niemals automatisch fachlich gleichsetzen.

---

## 5. Technische Grundentscheidung

Als Technologie wurde gewählt:

* **Python**
* **Streamlit** als lokale Oberfläche
* JSON-Dateien für Klassifikation, Alias- und Regelbasis
* CSV-/ZIP-Exports für Review- und Corpus-Auswertungen

Das Tool soll zunächst lokal/offline laufen.

Cloud-Deployment ist fachlich nicht bevorzugt, da Pflegeplandaten auch anonymisiert sensibel sind. Der lokale Betrieb ist für den Anfang der richtige Weg.

---

## 6. Entwicklungshistorie im Überblick

### Phase 1: XLSX-Import

Zu Beginn wurden Pflegepläne aus dem KIS als XLSX-Dateien getestet.

Dabei stellte sich heraus:

* Die KIS-XLSX-Dateien hatten kein normales Ein-Zeilen-Tabellenformat.
* Titel und Status/Zyklus standen teilweise in getrennten Zeilen.
* Abgesetzte Einträge wurden anfangs falsch erkannt.
* Details wurden teilweise als Pakete interpretiert.
* Mehrfach gleiche Leistungen wurden teilweise falsch zusammengeführt oder falsch dargestellt.
* Eigenschaften wie `PVK`, `Atemfrequenz`, `Wunde..`, `Dekubitus..`, `Antibiotikum` mussten als Details unter Leistungen behandelt werden.

Mehrere Parser-Versionen wurden entwickelt:

* v06 / v07: bessere Paket-/Leistungs-/Detail-Erkennung
* v08: eindeutige Leistungsinstanzen
* v08.1: Parser-Patch, z. B. für `Verlegung` als eigenes manuelles Paket

### Phase 2: Erste Engine

Mit v09 entstand eine erste Regel-Engine:

* Matching-Schicht
* Engine-Modelle
* Alias-Dateien
* LEP-Regeldateien
* Regelbefunde
* Unmatched-Listen

Die Engine konnte erste Befunde erzeugen:

* doppelte Planungen
* eingeschlossene Leistungen
* ausgeschlossene Leistungen als Prüfhilfe

Mit v09.3 wurden Regelbefunde gebündelt, damit nicht jede einzelne enthaltene Leistung als separate Zeile ausgegeben wird.

### Phase 3: Wechsel auf Grabber-TXT als Standard

Später wurde ein separates Tool namens **Grabber** entwickelt.

Grabber sammelt anonymisierte Pflegepläne aus dem KIS und speichert sie einheitlich als `.txt`.

Damit wurde entschieden:

**Grabber-TXT ist ab PRISMA v10 der Standardimport.**

Der alte XLSX-Weg ist damit nicht mehr der Hauptpfad.

---

## 7. Aktueller Stand: PRISMA v10.2

Die aktuelle Version ist:

**PRISMA v10.2**

Wichtige Dateien:

* `app.py`
* `parser.py`
* `engine/`
* `data/entry_classification.json`
* `data/lep_aliases.json`
* `data/lep_rules.json`
* `README.md`

Die App wird gestartet mit:

```powershell
python -m streamlit run app.py
```

---

## 8. Aktueller Standardimport: Grabber-TXT

Grabber-Dateien haben ungefähr folgende Struktur:

```text
Pflegeplan
Nachname: [ENTFERNT], Vorname: [ENTFERNT], [GEBDATUM ENTFERNT], Patientennummer: [ENTFERNT]

Systembenutzer: [ENTFERNT], Systemdatum: ..., Systemzeit: ...

Pfleg OE: ..., Fachabt.: ..., AnlegeDat.: ..., Startdat: ..., Endedat.: ...

Bezeichnung Pflegeplaneintrag    Status    Evaluierung    Zyklentext    AnlegeDat.    Erf.zeit    Angelegt von
 01 Bewegung (PMD)
Aktiv            11.05.2026    09:12    SADO
 Sturzrisiko: erhöht [1]
Aktiv            11.05.2026    09:12    SADO
 Sturzberatung durchführen
Aktiv        Einmalig-> 23:59 zur Selektion in Sicht    11.05.2026    09:12    SADO
```

Wichtig ist:

* Der Pflegeplaneintrag steht in einer Titelzeile.
* Der Status und der Zyklentext stehen in der darauffolgenden Zeile.
* Der Parser liest daher logische Paare:

  * Titelzeile
  * Status-/Zykluszeile

---

## 9. Parser-Logik aktuell

Der Parser soll:

* Grabber-TXT-Dateien lesen
* Metadaten erfassen

  * Pfleg OE
  * Fachabteilung
  * Systemdatum
  * Startdatum / Endedatum
* Einträge aus Titelzeile + Statuszeile bilden
* Einträge mit Status `Abgesetzt` ausblenden
* Einträge mit Status `Aktiv` verarbeiten
* Pakete erkennen
* Leistungen erkennen
* Details / Eigenschaften erkennen
* PMD-Pakete erkennen
* manuelle Pakete erkennen
* Zyklentexte übernehmen und grob interpretieren

Beispiele für Pakete:

* `01 Bewegung (PMD)`
* `02 Körperpflege (PMD)`
* `03 Ernährung (PMD)`
* `04 Ausscheidung (PMD)`
* `05 Kognition / Bewusstsein (PMD)`
* `07 Schlaf (PMD)`
* `09 Schmerz und emotionales Empfinden (PMD)`
* `10 Dekubitus/Wunde (PMD)`
* `11 Regulation von Körperfunktionen (PMD)`
* `Tagesroutine`
* `Aufnahme`
* `Verlegung`
* `OP Vorbereitung`
* `EQS Pneu`
* `PPR 2.0 Zusatzdaten`
* `Geräte und Hilfsmittel`
* `Überwachungen`
* `spezielle Überwachungen`
* `Infusionen 15/18/25`
* `VAC 15/18/25`
* `Redon 15/18/25`
* `Perfusoren 15/18/25`

Beispiele für Leistungen:

* `Vitalzeichen messen`
* `Schmerz überwachen`
* `Ausscheidung überwachen`
* `Infusion mit Zusatz verabreichen`
* `Wunde versorgen`
* `Wund-/Verbandkontrolle durchführen`
* `Sauerstoff verabreichen`
* `Inhalation unterstützen`
* `Atemtraining durchführen`
* `Abhusten unterstützen`
* `Medikament peroral verabreichen`

Beispiele für Details / Eigenschaften:

* `PVK`
* `ZVK`
* `PICCLINE`
* `Antibiotikum`
* `Elektrolyte`
* `Atemfrequenz`
* `Puls messen`
* `Blutdruck messen`
* `Körpertemperatur messen`
* `Wunde..`
* `Dekubitus..`
* `Prevena`
* `mit VAC Pumpe`
* `Antikoagulation`

Details dürfen nicht wie eigenständige Leistungen bewertet werden. Sie dienen dazu, Leistungsinstanzen besser zu unterscheiden.

---

## 10. Corpus-Auswertung

Mit v10.1 und v10.2 wurde eine Corpus-Auswertung eingeführt.

Corpus bedeutet:

Eine Sammlung vieler Pflegepläne wird gemeinsam analysiert.

Beispiele:

* `Set01.zip`
* `Set02.zip`
* später alle Pflegepläne einer Station oder Abteilung

Bisherige große Testsets:

### Set01

Chirurgielastig:

* Station 15 – THG
* Station 18 – THG/UCH
* Station 22 – KAR
* Station 25 – THG

Insgesamt: 82 Pflegepläne

### Set02

Mehr internistisch:

* Station 21 – GAS/END
* Station 31 – DER
* Station 32 – NPH/RHT/KAR
* Station 33 – HAE/NEU/STR

Insgesamt: 90 Pflegepläne

Zusammen: 172 Pflegepläne

Früherer Schnelltest:

* 172 Dateien verarbeitet
* 0 Parser-Fehler
* ca. 13.221 Parser-Einträge
* ca. 1.618 Pakete
* ca. 7.164 Leistungen
* ca. 4.439 Details / Eigenschaften
* ca. 6.630 gematchte Leistungen
* ca. 534 unmatched Leistungen
* Match-Rate ca. 92,55 %

---

## 11. Sinn der Corpus-Auswertung

Die Corpus-Auswertung soll zeigen:

* Wie viele Pflegepläne wurden verarbeitet?
* Welche Stationen / Fachbereiche sind enthalten?
* Welche Pakete kommen häufig vor?
* Welche Leistungen kommen häufig vor?
* Welche Details / Eigenschaften kommen häufig vor?
* Welche Leistungen sind unbekannt?
* Welche unbekannten Einträge kommen am häufigsten vor?
* Welche Einträge brauchen manuelle Klassifikation?
* Welche Stationen/Fachbereiche erzeugen besonders viele unbekannte Einträge?
* Wo sollte die Wissensbasis zuerst erweitert werden?

Wichtig:

Die Corpus-Auswertung ist **keine automatische Zuordnungsmaschine**.

Sie findet Lücken.
Menschen und verifizierte LEP-Daten schließen diese Lücken.

---

## 12. v10.2: Review-/Sortierliste für unbekannte Einträge

In v10.2 wurde die Reviewliste verbessert.

Unbekannte Einträge werden nicht als Fehler behandelt, sondern als:

```text
needs_manual_classification
```

Die Reviewliste enthält zusätzliche Spalten:

* Review-Kategorie
* Review-Klasse
* Vermutete Ursache
* Review-Priorität
* Prüffrage
* Manuelle Entscheidung
* Team-Kommentar
* Auto-Match erlaubt

Auto-Match ist immer:

```text
False
```

---

## 13. Review-Kategorien in v10.2

Unbekannte Einträge werden konservativ vorsortiert.

Diese Sortierung ist **kein Match** und keine fachliche Gleichsetzung.

Kategorien:

### 1. Unbekannte Leistung / fachlich zuordnen

Eintrag wirkt wie eine eigenständige Leistung, ist aber noch nicht bekannt.

Prüffrage:

Ist dies eine LEP-Leistung, eine hausinterne Leistung oder ein Spezialstandard?

### 2. Mögliches Detail / Eigenschaft

Eintrag wirkt eher wie eine Eigenschaft oder ein Detail.

Beispiele:

* `PVK`
* `ZVK`
* `Atemfrequenz`
* `Wunde..`
* `Dekubitus..`

Prüffrage:

Gehört dieser Eintrag unter eine konkrete Leistung?

### 3. Möglicherweise hausintern / organisatorisch

Eintrag wirkt wie ein lokaler Ablaufstandard oder organisatorischer Nachweis.

Beispiele:

* `Bettplatz vor-/nachbereiten`
* `Eintritt organisieren`
* `Patienteneigentum ein-/auspacken`

### 4. Strukturell auffällig / Planungslogik prüfen

Eintrag ist nicht eindeutig falsch, wirkt aber strukturell verdächtig.

Prüffrage:

Steht dieser Eintrag im passenden Paket und an der richtigen Stelle?

### 5. PMD-Kontext prüfen

Unbekannter Eintrag liegt in einem PMD-Paket.

Prüffrage:

Ist dies eine echte Leistung, ein Problem-/Ausprägungstext oder ein automatisch abgeleiteter Detailkontext?

### 6. Fachbereichsspezifisch prüfen

Eintrag könnte in bestimmten Fachbereichen üblich sein, etwa GAS/END, DER, KAR, NPH, HAE, NEU usw.

Prüffrage:

Ist dies eine fachbereichsspezifische Leistung, die bewusst als eigene Maßnahme existiert?

---

## 14. Klassifikationslogik

Die Datei:

```text
data/entry_classification.json
```

enthält Klassifikationen für Pakete und Fallbacks.

Wichtige Kategorien:

* `pmd_auto_package`
* `house_internal_standard`
* `qm_compliance_marker`
* `ppr_marker`
* `manual_package`
* `house_internal_procedure_package`
* `local_known`
* `lep_verified`
* `needs_manual_classification`
* `unknown_or_needs_review`

Beispiele:

`EQS Pneu`

Kategorie:

```text
QM-/Nachweis-Paket
```

`PPR 2.0 Zusatzdaten`

Kategorie:

```text
PPR-/Einstufungslogik
```

`Tagesroutine`, `Aufnahme`, `Verlegung`, `OP Vorbereitung`

Kategorie:

```text
Hausinterner Standard
```

`Geräte und Hilfsmittel`, `Überwachungen`, `spezielle Überwachungen`

Kategorie:

```text
Manuelles Paket
```

`Infusionen 15/18/25`, `VAC 15/18/25`, `Redon 15/18/25`, `Perfusoren 15/18/25`

Kategorie:

```text
Hausinternes Maßnahmenpaket
```

---

## 15. Matching

Matching basiert auf vorhandenen Alias- und Regeldateien.

Es gibt:

* lokale Matches
* verifizierte LEP-Matches
* unbekannte Einträge

Wichtig:

Ein lokaler Match bedeutet:

PRISMA kennt diesen Titel lokal, aber er ist nicht zwingend LEP-verifiziert.

Ein verifizierter Match bedeutet:

Der Eintrag ist mit einer echten LEP-ID oder bestätigten LEP-Regel verbunden.

Ein unbekannter Eintrag bedeutet:

Der Eintrag wurde nicht klassifiziert und muss manuell geprüft werden.

Unbekannt bedeutet nicht automatisch:

* falsch
* nicht im LEP
* schlechte Pflegeplanung

Es bedeutet nur:

PRISMA kann ihn aktuell nicht sicher einordnen.

---

## 16. Regel-Engine

Die erste Regel-Engine existiert seit v09.x und wurde in die späteren Versionen übernommen.

Sie kann grundsätzlich:

* doppelte Planungen erkennen
* eingeschlossene Leistungen erkennen
* ausgeschlossene Leistungen als Prüfhilfe anzeigen
* Regelbefunde bündeln

Beispiele für Regelideen:

* Leistung B ist in Leistung A enthalten.
* Mehrere geplante Einzelleistungen könnten durch eine übergeordnete Leistung abgedeckt sein.
* Eine ausgeschlossene Leistung ist nicht automatisch fehlend, sondern separat zu prüfen.

Wichtig:

Ausgeschlossene LEP-Leistung bedeutet nicht automatisch:

```text
Fehler
```

sondern eher:

```text
Nicht enthalten / separat prüfen
```

---

## 17. Fachliche Zielrichtung der Engine

PRISMA soll langfristig nicht nur sagen:

* bekannt
* unbekannt

sondern differenzieren:

* LEP-verifiziert
* lokal bekannt
* hausintern
* PMD-generiert
* PPR-/Einstufungslogik
* QM-/Nachweislogik
* Detail/Eigenschaft
* strukturell auffällig
* ungeklärt / manuell zu prüfen

Nur wenn eine Leistung LEP-verifiziert ist, kann PRISMA belastbare LEP-Einschluss-/Ausschlusslogik anwenden.

---

## 18. Wichtige offene Aufgaben

### 1. Reviewliste weiter auswerten

Die Sortierliste aus v10.2 soll manuell geprüft werden.

Ziel:

* unbekannte Einträge in Kategorien sortieren
* echte LEP-Leistungen identifizieren
* hausinterne Leistungen markieren
* Details/Eigenschaften sauber klassifizieren
* strukturelle Auffälligkeiten sichtbar machen

### 2. Entry Classification erweitern

Die Datei `entry_classification.json` soll schrittweise erweitert werden.

### 3. Aliasbasis erweitern

Aber nur manuell geprüft.

Keine automatischen Ähnlichkeitsmatches.

### 4. Mehr LEP-verifizierte Matches

Viele Matches sind aktuell lokal bekannt, aber noch nicht LEP-verifiziert.

Für echte Regelqualität müssen mehr LEP-IDs ergänzt werden.

### 5. Regel-Engine ausbauen

Mögliche spätere Regeln:

* bessere Bündelung von enthaltenen Leistungen
* Vorschläge wie:

  * „Plane stattdessen Leistung X, weil diese mehrere aktuelle Einzelleistungen abdeckt.“
* strengere Dublettenerkennung
* hausinterne Sonderregeln
* PPR-2.0-Mapping

### 6. PPR-2.0-Mapping anbinden

Später soll die vorhandene PPR-2.0-Mapping-Tabelle integriert werden.

Dann kann PRISMA zusätzlich prüfen:

* Welche Leistungen sind PPR-relevant?
* Welche Zusatzitems fehlen?
* Welche Detailinformationen sind relevant?
* Welche PMD-Ausleitungen wirken unvollständig oder übermäßig?

---

## 19. Gewünschter Arbeitsstil für zukünftige KI / Copilot

Bitte bei Weiterentwicklung beachten:

1. Konservativ arbeiten.
2. Keine automatischen Fuzzy-Zuordnungen.
3. Keine ähnlichen Leistungen zusammenführen.
4. Unbekannte Leistungen als Review-Items behandeln.
5. Parser und Engine getrennt halten.
6. Grabber-TXT als Standardimport verwenden.
7. XLSX nur noch als Altpfad betrachten, nicht als Hauptentwicklung.
8. Jede neue Klassifikation nachvollziehbar machen.
9. Regelbefunde müssen erklärbar sein.
10. Keine Blackbox-Logik.

---

## 20. Aktuelle Projektformel

Der aktuelle Standardfluss ist:

```text
Grabber .txt
→ PRISMA Parser v10.2
→ Entry Classification
→ Matching / Aliasbasis
→ Regel-Engine
→ Einzelanalyse oder Corpus-Auswertung
→ Review-/Sortierliste
→ manuelle Klassifikation
→ spätere Erweiterung der Wissensbasis
```

---

## 21. Wichtigste Erkenntnis

PRISMA soll nicht einfach nur Pflegepläne „lesen“.

PRISMA soll die reale Pflegeplanungswelt des Krankenhauses fachlich sauber kartografieren:

* Was ist LEP?
* Was ist hausintern?
* Was ist PMD?
* Was ist PPR?
* Was ist Nachweislogik?
* Was ist Detail?
* Was ist strukturell auffällig?
* Was ist noch ungeklärt?

Erst auf dieser sauberen Grundlage kann PRISMA später zuverlässig Hinweise zu Dubletten, eingeschlossenen Leistungen, ausgeschlossenen Leistungen und PPR-Relevanz geben.

---

## 22. Aktueller Stand in einem Satz

**PRISMA v10.2 ist ein funktionierender Streamlit-Prototyp mit Grabber-TXT-Import, Einzelplananalyse, Corpus-Auswertung, konservativer Matchinglogik ohne automatische Ähnlichkeitszuordnung und einer verbesserten Review-/Sortierliste für unbekannte oder strukturell auffällige Pflegeplaneinträge.**
