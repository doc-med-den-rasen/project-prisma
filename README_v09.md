# PRISMA v09

## Inhalt
- `prisma_parser_v08_1.py` -> Parser mit kleinem Patch für `Verlegung`
- `prisma_app_v09.py` -> Streamlit-App
- `engine/` -> Matcher, Engine, Modelle, Regeln
- `data/` -> LEP-Regeln, Alias-Mapping, Engine-Konfiguration

## Start
```powershell
python -m streamlit run prisma_app_v09.py
```

## Hinweise
- `lep_rules_v09.json` ist absichtlich nur ein erster Ausschnitt.
- Die erste Engine ist ein Grundgerüst, kein Vollausbau.
- Gute nächste Schritte:
  1. Alias-Datei ausbauen
  2. LEP-Regeln schrittweise erweitern
  3. Findings optisch priorisieren
