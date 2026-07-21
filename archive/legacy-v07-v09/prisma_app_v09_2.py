"""
PRISMA - App v09.2
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
from engine.engine_v09_2 import run_engine_v09_2

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
LEP_RULES_PATH = DATA_DIR / "lep_rules_v09_2.json"
LEP_ALIASES_PATH = DATA_DIR / "lep_aliases_v09_2.json"
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
                "Match-Typ": entry.matched.match_type if entry.matched else "unmatched",
                "Match-Quelle": "lokal/provisorisch" if str(lep_id).startswith("LOCAL_") else ("LEP/verifiziert" if lep_id else ""),
                "Confidence": entry.matched.confidence if entry.matched else 0.0,
                "Top-Vorschlag": top_suggestion,
                "Vorschlags-Score": top_score,
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
                "Schwere": finding.severity,
                "Paket": finding.package,
                "Primär": finding.title_primary,
                "Sekundär": finding.title_secondary,
                "Meldung": finding.message,
                "Confidence": finding.confidence,
            }
        )
    return pd.DataFrame(rows)


def unmatched_to_dataframe(unmatched_entries: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in unmatched_entries:
        suggestion_titles = " | ".join(
            f"{s['lep_title']} ({s['score']})" for s in item.get("suggestions", [])[:3]
        )
        rows.append(
            {
                "Eintrag-ID": item.get("entry_id"),
                "Paket": item.get("package"),
                "Anzeige": item.get("display_title"),
                "Details": ", ".join(item.get("details", [])),
                "Zyklentext": item.get("zyklentext"),
                "Vorschläge": suggestion_titles,
            }
        )
    return pd.DataFrame(rows)


st.set_page_config(page_title="PRISMA v09.2", page_icon="🔷", layout="wide")

st.title("🔷 PRISMA v09.2")
st.caption("Match-Ausbau mit größerer Alias-Basis und robusterem Titelabgleich")

with st.expander("Was in v09.2 neu ist", expanded=False):
    st.markdown(
        """
- **größere Alias-Basis** aus mehreren Unmatched-Exporten
- **Instanz-Suffixe** wie `[1/2]` werden im Matching sauber normalisiert
- **Match-Quelle** wird angezeigt: verifiziert vs. lokal/provisorisch
- Included/Excluded-Regeln bleiben bewusst am stärksten bei **verifizierten LEP-Einträgen**
"""
    )

uploaded_file = st.file_uploader("Pflegeplan als XLSX hochladen", type=["xlsx"])

if uploaded_file is None:
    st.info("Lade eine XLSX-Datei hoch, um PRISMA v09.2 zu starten.")
    st.stop()

try:
    temp_path = save_uploaded_file_temporarily(uploaded_file)
    parser_entries, parser_stats = parse_pflegeplan_xlsx_v08_1(temp_path)
    engine_result = run_engine_v09_2(parser_entries, LEP_RULES_PATH, LEP_ALIASES_PATH)

    df_parser = parser_entries_to_dataframe(parser_entries)
    df_matches = matched_entries_to_dataframe(engine_result["parsed_entries"])
    df_findings = findings_to_dataframe(engine_result["findings"])
    df_unmatched = unmatched_to_dataframe(engine_result["unmatched_entries"])
    df_unmatched_summary = pd.read_csv(UNMATCHED_SUMMARY_PATH, sep=";") if UNMATCHED_SUMMARY_PATH.exists() else pd.DataFrame()
except Exception as exc:
    st.error("Beim Einlesen oder Auswerten der Datei ist ein Fehler aufgetreten.")
    st.exception(exc)
    st.stop()

match_summary = engine_result["match_summary"]
rule_summary = engine_result["rule_summary"]

col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Parser-Einträge", len(df_parser))
col2.metric("Gematchte Leistungen", match_summary["matched_count"])
col3.metric("Verifizierte Matches", match_summary["verified_match_count"])
col4.metric("Lokale Matches", match_summary["local_match_count"])
col5.metric("Unmatched Leistungen", match_summary["unmatched_count"])
col6.metric("Match-Rate", f"{match_summary['match_rate']} %")

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
        st.success("Keine unmatched Leistungen in der aktuellen Datei.")
    else:
        st.dataframe(df_unmatched, use_container_width=True, hide_index=True)
        st.caption("Die Vorschläge sind Hinweise. v09.2 hebt die Match-Rate vor allem über eine breitere Alias-Basis an.")

with tab4:
    st.subheader("Basis für weitere Alias-Pflege")
    if df_unmatched_summary.empty:
        st.info("Keine vorbereitete Unmatched-Zusammenfassung vorhanden.")
    else:
        st.dataframe(df_unmatched_summary, use_container_width=True, hide_index=True)

with tab5:
    st.subheader("Regelbefunde")
    if df_findings.empty:
        st.info("Noch keine Befunde. Das kann bedeuten: keine passende Regel oder keine Auffälligkeit.")
    else:
        severity_filter = st.multiselect(
            "Schwere filtern",
            options=sorted(df_findings["Schwere"].dropna().unique().tolist()),
            default=sorted(df_findings["Schwere"].dropna().unique().tolist()),
        )
        filtered = df_findings[df_findings["Schwere"].isin(severity_filter)] if severity_filter else df_findings
        st.dataframe(filtered, use_container_width=True, hide_index=True)

with tab6:
    st.subheader("Technische Statistik")

    st.markdown("**Parser-Statistik**")
    parser_stats_df = pd.DataFrame(
        [{"Kennzahl": key, "Wert": json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value}
         for key, value in parser_stats.items()]
    )
    st.dataframe(parser_stats_df, use_container_width=True, hide_index=True)

    st.markdown("**Engine-Statistik**")
    engine_stats = [
        {"Kennzahl": "service_count", "Wert": match_summary["service_count"]},
        {"Kennzahl": "matched_count", "Wert": match_summary["matched_count"]},
        {"Kennzahl": "verified_match_count", "Wert": match_summary["verified_match_count"]},
        {"Kennzahl": "local_match_count", "Wert": match_summary["local_match_count"]},
        {"Kennzahl": "unmatched_count", "Wert": match_summary["unmatched_count"]},
        {"Kennzahl": "match_rate", "Wert": match_summary["match_rate"]},
        {"Kennzahl": "findings_duplicate_same_service", "Wert": rule_summary["by_type"]["duplicate_same_service"]},
        {"Kennzahl": "findings_included_redundancy", "Wert": rule_summary["by_type"]["included_redundancy"]},
        {"Kennzahl": "findings_excluded_but_separate_check", "Wert": rule_summary["by_type"]["excluded_but_separate_check"]},
    ]
    st.dataframe(pd.DataFrame(engine_stats), use_container_width=True, hide_index=True)

    st.markdown("**Unmatched nach Paket**")
    unmatched_pkg_df = pd.DataFrame(
        [{"Paket": key, "Unmatched": value} for key, value in match_summary["unmatched_by_package"].items()]
    )
    if unmatched_pkg_df.empty:
        st.success("Keine unmatched Pakete.")
    else:
        st.dataframe(unmatched_pkg_df, use_container_width=True, hide_index=True)

    st.markdown("**Match-Status pro Paket**")
    pkg_rows = []
    for pkg, values in match_summary["match_by_package"].items():
        pkg_rows.append({"Paket": pkg, "Matched": values["matched"], "Unmatched": values["unmatched"]})
    pkg_df = pd.DataFrame(pkg_rows)
    if pkg_df.empty:
        st.info("Noch keine Paket-Statistik.")
    else:
        st.dataframe(pkg_df, use_container_width=True, hide_index=True)

st.divider()
st.success("PRISMA v09.2 geladen.")
