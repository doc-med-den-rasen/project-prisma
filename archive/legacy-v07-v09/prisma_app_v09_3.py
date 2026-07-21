
"""
PRISMA - App v09.3
==================
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from prisma_parser_v08_1 import parse_pflegeplan_xlsx_v08_1
from engine.engine_v09_3 import run_engine_v09_3

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
LEP_RULES_PATH = DATA_DIR / "lep_rules_v09_3.json"
LEP_ALIASES_PATH = DATA_DIR / "lep_aliases_v09_3.json"
UNMATCHED_SUMMARY_PATH = DATA_DIR / "unmatched_summary_v09_2.csv"


def save_uploaded_file_temporarily(uploaded_file) -> Path:
    suffix = Path(uploaded_file.name).suffix or ".xlsx"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getbuffer())
        return Path(tmp.name)


def parser_entries_to_dataframe(entries: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for entry in entries:
        zyklus_info = entry.get("zyklus_info", {}) or {}
        rows.append(
            {
                "Eintrag-ID": entry.get("entry_id"),
                "Parent-ID": entry.get("parent_entry_id"),
                "Titel-Zeile": entry.get("title_row"),
                "Status-Zeile": entry.get("status_row"),
                "Paket": entry.get("package"),
                "Herkunft": entry.get("entry_origin"),
                "Typ": entry.get("row_type"),
                "Eintrag": entry.get("title"),
                "Anzeige": entry.get("display_title"),
                "Zyklentext": entry.get("zyklentext"),
                "Zyklus-Typ": zyklus_info.get("kind"),
                "Instanz": entry.get("instance_index"),
                "Instanzen gesamt": entry.get("instance_total_same_title"),
            }
        )
    return pd.DataFrame(rows)


def matched_entries_to_dataframe(parsed_entries) -> pd.DataFrame:
    rows = []
    for entry in parsed_entries:
        if entry.entry_type != "leistung":
            continue
        suggestions = entry.matched.suggestions if entry.matched else []
        top_suggestion = suggestions[0].lep_title if suggestions else ""
        top_score = suggestions[0].score if suggestions else ""
        lep_id = entry.matched.lep_id if entry.matched else ""
        rows.append(
            {
                "Eintrag-ID": entry.entry_id,
                "Paket": entry.package,
                "Anzeige": entry.display_title,
                "Details": ", ".join(entry.details),
                "Zyklentext": entry.zyklentext,
                "LEP-ID": lep_id,
                "LEP-Titel": entry.matched.lep_title if entry.matched else "",
                "Match-Typ": entry.matched.match_type if entry.matched else "",
                "Confidence": entry.matched.confidence if entry.matched else "",
                "Top-Suggestion": top_suggestion,
                "Top-Score": top_score,
            }
        )
    return pd.DataFrame(rows)


def unmatched_entries_to_dataframe(unmatched_entries: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in unmatched_entries:
        suggestion_text = " | ".join(
            f"{s['lep_title']} ({s['score']})" for s in item.get("suggestions", [])[:3]
        )
        rows.append(
            {
                "Eintrag-ID": item.get("entry_id"),
                "Paket": item.get("package"),
                "Anzeige": item.get("display_title"),
                "Details": ", ".join(item.get("details", [])),
                "Zyklentext": item.get("zyklentext"),
                "Vorschläge": suggestion_text,
            }
        )
    return pd.DataFrame(rows)


def findings_to_dataframe(findings) -> pd.DataFrame:
    rows = []
    for finding in findings:
        rows.append(
            {
                "Finding-ID": finding.finding_id,
                "Regeltyp": finding.rule_type,
                "Schweregrad": finding.severity,
                "Paket": finding.package,
                "Primär-Eintrag": finding.title_primary,
                "Sekundär-Eintrag": finding.title_secondary or "",
                "Meldung": finding.message,
                "Empfehlung": finding.recommendation,
                "Confidence": finding.confidence,
                "Payload": json.dumps(finding.payload, ensure_ascii=False),
            }
        )
    return pd.DataFrame(rows)


st.set_page_config(page_title="PRISMA v09.3", page_icon="🔷", layout="wide")

st.title("🔷 PRISMA v09.3")
st.caption("Gebündelte Regelbefunde, zusätzliche lokale Aliase und klarere Behandlung von Spezialfällen")

with st.expander("Was in v09.3 neu ist", expanded=False):
    st.markdown(
        """
- Wiederkehrende **Unmatched-Leistungen** aus den Testläufen wurden lokal ergänzt
- **Regelbefunde werden gebündelt**, statt für jede enthaltene Einzelleistung eine neue Zeile zu erzeugen
- **Empfehlungen** werden direkt in den Regelbefunden angezeigt
- Bei Plänen **ohne aktive Leistungszeilen** wird die Match-Rate nicht als `0 %`, sondern als `n/a` behandelt
"""
    )

uploaded_file = st.file_uploader("Pflegeplan als XLSX hochladen", type=["xlsx"])

if uploaded_file is None:
    st.info("Lade eine XLSX-Datei hoch, um die Analyse zu starten.")
    st.stop()

temp_path = save_uploaded_file_temporarily(uploaded_file)
parser_entries, parser_stats = parse_pflegeplan_xlsx_v08_1(temp_path)
engine_result = run_engine_v09_3(parser_entries, LEP_RULES_PATH, LEP_ALIASES_PATH)

df_parser = parser_entries_to_dataframe(parser_entries)
df_matches = matched_entries_to_dataframe(engine_result["parsed_entries"])
df_unmatched = unmatched_entries_to_dataframe(engine_result["unmatched_entries"])
df_findings = findings_to_dataframe(engine_result["findings"])

match_summary = engine_result["match_summary"]
rule_summary = engine_result["rule_summary"]

col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Parser-Einträge", len(df_parser))
col2.metric("Gematchte Leistungen", match_summary["matched_count"])
col3.metric("Verifizierte Matches", match_summary["verified_match_count"])
col4.metric("Lokale Matches", match_summary["local_match_count"])
col5.metric("Unmatched Leistungen", match_summary["unmatched_count"])
match_rate_display = "n/a" if match_summary["match_rate"] is None else f"{match_summary['match_rate']} %"
col6.metric("Match-Rate", match_rate_display)

if match_summary["service_count"] == 0:
    st.info("In diesem Plan wurden keine aktiven Leistungszeilen erkannt. Das ist eher ein PMD-/Eigenschaftsrest als ein klassischer Leistungsplan. Deshalb ist die Match-Rate hier nicht aussagekräftig.")

st.divider()

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Parser", "Matches", "Unmatched", "Alias-Basis", "Regelbefunde", "Statistik"])

with tab1:
    st.subheader("Parser-Ausgabe")
    st.dataframe(df_parser, use_container_width=True, hide_index=True)

with tab2:
    st.subheader("LEP-Matching")
    if df_matches.empty:
        st.info("Keine Leistungen zum Matching vorhanden.")
    else:
        st.dataframe(df_matches, use_container_width=True, hide_index=True)

with tab3:
    st.subheader("Unmatched Leistungen")
    if df_unmatched.empty:
        st.success("Keine unmatched Leistungen vorhanden.")
    else:
        st.dataframe(df_unmatched, use_container_width=True, hide_index=True)

with tab4:
    st.subheader("Alias-Basis")
    if LEP_ALIASES_PATH.exists():
        alias_data = json.loads(LEP_ALIASES_PATH.read_text(encoding="utf-8"))
        alias_rows = []
        for alias in alias_data.get("aliases", []):
            alias_rows.append(
                {
                    "PRISMA-Titel": alias.get("prisma_title"),
                    "LEP-Titel": alias.get("lep_title"),
                    "LEP-ID": alias.get("lep_id"),
                    "Scope": ", ".join(alias.get("package_scopes", [])),
                    "Synonyme": ", ".join(alias.get("synonyms", [])),
                }
            )
        st.dataframe(pd.DataFrame(alias_rows), use_container_width=True, hide_index=True)

with tab5:
    st.subheader("Regelbefunde")
    if df_findings.empty:
        st.success("Keine Regelbefunde gefunden.")
    else:
        st.dataframe(df_findings, use_container_width=True, hide_index=True)

with tab6:
    st.subheader("Statistik")
    stat_rows = []
    for key, value in parser_stats.items():
        stat_rows.append({"Bereich": "Parser", "Kennzahl": key, "Wert": json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value})
    for key, value in match_summary.items():
        stat_rows.append({"Bereich": "Matching", "Kennzahl": key, "Wert": json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value})
    for key, value in rule_summary.items():
        stat_rows.append({"Bereich": "Engine", "Kennzahl": key, "Wert": json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value})
    st.dataframe(pd.DataFrame(stat_rows), use_container_width=True, hide_index=True)

st.divider()
st.success("PRISMA v09.3 geladen.")
