"""
PRISMA - Streamlit App v07
==========================

v07 nutzt den Parser, der pro Paket die letzte aktive Version verwendet.
Dadurch werden doppelte PMD- und manuelle Pakete über den Aufenthalt hinweg
deutlich sauberer dargestellt.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from prisma_parser_v07 import parse_pflegeplan_xlsx_v07


# ============================================================
# STREAMLIT-KONFIGURATION
# ============================================================

st.set_page_config(
    page_title="PRISMA v07",
    page_icon="🔷",
    layout="wide",
)


# ============================================================
# HILFSFUNKTIONEN
# ============================================================

def save_uploaded_file_temporarily(uploaded_file) -> Path:
    """Speichert die hochgeladene XLSX-Datei temporär auf der Platte."""
    suffix = Path(uploaded_file.name).suffix or ".xlsx"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getbuffer())
        return Path(tmp.name)


def entries_to_dataframe(entries: List[Dict[str, Any]]) -> pd.DataFrame:
    """Wandelt Parser-Einträge in eine DataFrame-Struktur um."""
    rows = []

    for entry in entries:
        zyklus_info = entry.get("zyklus_info", {}) or {}

        rows.append(
            {
                "Titel-Zeile": entry.get("title_row"),
                "Status-Zeile": entry.get("status_row"),
                "Paket": entry.get("package"),
                "Paket (roh)": entry.get("package_raw"),
                "Herkunft": entry.get("entry_origin"),
                "Paket ist PMD": entry.get("package_is_pmd"),
                "Typ": entry.get("row_type"),
                "Eintrag": entry.get("title"),
                "Übergeordnete Leistung": entry.get("parent_leistung"),
                "Status": entry.get("status"),
                "Zyklentext": entry.get("zyklentext"),
                "Zyklus-Typ": zyklus_info.get("kind"),
                "Frequenz/Tag": zyklus_info.get("frequency_per_day"),
                "Intervall (Stunden)": zyklus_info.get("interval_hours"),
                "Uhrzeiten": ", ".join(zyklus_info.get("times", [])) if zyklus_info.get("times") else "",
                "Zyklus-Notiz": zyklus_info.get("notes"),
                "Geplantes Kernelement": entry.get("is_planned_core", False),
                "Im Aufenthalt gefunden": entry.get("package_seen_anywhere_in_stay"),
                "Paket-Vorkommen im Aufenthalt": entry.get("package_occurrences_in_stay"),
            }
        )

    df = pd.DataFrame(rows)

    if not df.empty:
        df["Hat Zyklentext"] = df["Zyklentext"].fillna("").astype(str).str.strip().ne("")

    return df


def build_summary(df: pd.DataFrame) -> Dict[str, int]:
    """Erzeugt Kennzahlen für die sichtbare Ansicht."""
    if df.empty:
        return {
            "gesamt": 0,
            "pakete": 0,
            "leistungen": 0,
            "details": 0,
            "pmd": 0,
            "manuell": 0,
            "mit_zyklus": 0,
        }

    return {
        "gesamt": int(len(df)),
        "pakete": int((df["Typ"] == "paket").sum()),
        "leistungen": int((df["Typ"] == "leistung").sum()),
        "details": int((df["Typ"] == "detail").sum()),
        "pmd": int((df["Herkunft"] == "PMD").sum()),
        "manuell": int((df["Herkunft"] == "manuell").sum()),
        "mit_zyklus": int(df["Hat Zyklentext"].sum()),
    }


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Exportiert die aktuelle Ansicht als CSV."""
    return df.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")


def dataframe_to_json_bytes(df: pd.DataFrame) -> bytes:
    """Exportiert die aktuelle Ansicht als JSON."""
    return json.dumps(
        df.to_dict(orient="records"),
        indent=2,
        ensure_ascii=False,
    ).encode("utf-8")


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Baut die Sidebar-Filter und liefert die sichtbare Ansicht zurück."""
    st.sidebar.header("Filter")

    if df.empty:
        return df

    type_options = [t for t in ["paket", "leistung", "detail"] if t in df["Typ"].dropna().unique().tolist()]
    selected_types = st.sidebar.multiselect(
        "Eintragstyp",
        options=type_options,
        default=type_options,
        help="v07 zeigt standardmäßig auch Details/Eigenschaften, damit man gleiche Leistungen besser unterscheiden kann.",
    )

    origin_options = sorted(df["Herkunft"].dropna().unique().tolist())
    selected_origin = st.sidebar.multiselect(
        "Herkunft",
        options=origin_options,
        default=origin_options,
    )

    package_options = sorted([p for p in df["Paket"].dropna().unique().tolist() if str(p).strip()])
    selected_packages = st.sidebar.multiselect(
        "Pakete",
        options=package_options,
        default=package_options,
    )

    only_with_zyklus = st.sidebar.checkbox(
        "Nur Einträge mit Zyklentext anzeigen",
        value=False,
    )

    search_term = st.sidebar.text_input(
        "Suche",
        placeholder="z. B. VAC, Schmerz, Ernährung, Aufnahme...",
    ).strip()

    filtered = df.copy()

    if selected_types:
        filtered = filtered[filtered["Typ"].isin(selected_types)]

    if selected_origin:
        filtered = filtered[filtered["Herkunft"].isin(selected_origin)]

    if selected_packages:
        filtered = filtered[filtered["Paket"].fillna("").isin(selected_packages)]

    if only_with_zyklus:
        filtered = filtered[filtered["Hat Zyklentext"] == True]

    if search_term:
        mask = (
            filtered["Eintrag"].fillna("").str.contains(search_term, case=False, na=False)
            | filtered["Paket"].fillna("").str.contains(search_term, case=False, na=False)
            | filtered["Zyklentext"].fillna("").str.contains(search_term, case=False, na=False)
            | filtered["Übergeordnete Leistung"].fillna("").str.contains(search_term, case=False, na=False)
        )
        filtered = filtered[mask]

    return filtered


def render_tree_view(df: pd.DataFrame) -> None:
    """
    Stellt den Pflegeplan gruppiert nach Paket dar.

    v07 zeigt:
    - Paket
    - paketnahe Details/Eigenschaften
    - Leistungen
    - leistungsnahe Details/Eigenschaften
    """
    if df.empty:
        st.info("Keine Einträge für die Baumansicht vorhanden.")
        return

    pakete_df = df[df["Typ"] == "paket"].copy()

    if pakete_df.empty:
        st.warning("Es wurden in der aktuellen Ansicht keine Pakete gefunden.")
        return

    for _, paket_row in pakete_df.iterrows():
        paket_name = paket_row["Eintrag"]
        paket_clean = paket_row["Paket"] or paket_name
        herkunft = paket_row["Herkunft"]
        vorkommen = paket_row.get("Paket-Vorkommen im Aufenthalt", "")

        with st.expander(f"📦 {paket_name}  ·  Herkunft: {herkunft}  ·  Vorkommen im Aufenthalt: {vorkommen}", expanded=False):
            paket_details = df[
                (df["Paket"] == paket_clean) &
                (df["Typ"] == "detail") &
                (df["Übergeordnete Leistung"].isna() | df["Übergeordnete Leistung"].eq(""))
            ].copy()

            if not paket_details.empty:
                st.markdown("**Paketdetails / Probleme / Eigenschaften**")
                for _, detail_row in paket_details.iterrows():
                    st.markdown(f"- {detail_row['Eintrag']}")

            leistungen = df[
                (df["Paket"] == paket_clean) &
                (df["Typ"] == "leistung")
            ].copy()

            if leistungen.empty:
                st.caption("Keine sichtbaren Leistungen in diesem Paket.")
                continue

            st.markdown("**Leistungen**")
            for _, leistung_row in leistungen.iterrows():
                leistung_name = str(leistung_row["Eintrag"])
                zyklus = str(leistung_row["Zyklentext"] or "").strip()

                if zyklus:
                    st.markdown(f"- **{leistung_name}**  \n  Zyklus: `{zyklus}`")
                else:
                    st.markdown(f"- **{leistung_name}**")

                details = df[
                    (df["Paket"] == paket_clean) &
                    (df["Typ"] == "detail") &
                    (df["Übergeordnete Leistung"] == leistung_name)
                ].copy()

                for _, detail_row in details.iterrows():
                    st.markdown(f"   - {detail_row['Eintrag']}")


def build_marker_table(df_all: pd.DataFrame) -> pd.DataFrame:
    """
    Baut eine kleine Marker-Tabelle für wichtige Pakete auf.
    """
    marker_packages = [
        "EQS Pneu",
        "PPR 2.0 Zusatzdaten",
    ]

    rows = []
    for pkg in marker_packages:
        pkg_df = df_all[df_all["Paket"] == pkg]
        rows.append(
            {
                "Paket": pkg,
                "Aktuell sichtbar/aktiv": not pkg_df.empty,
                "Im Aufenthalt gefunden": bool(pkg_df["Im Aufenthalt gefunden"].any()) if not pkg_df.empty else False,
                "Vorkommen im Aufenthalt": int(pkg_df["Paket-Vorkommen im Aufenthalt"].max()) if not pkg_df.empty else 0,
            }
        )

    return pd.DataFrame(rows)


# ============================================================
# HAUPT-UI
# ============================================================

st.title("🔷 PRISMA v07")
st.caption("Pflegeplan-Regelwerk zur Interventions-, Struktur- und Mapping-Analyse")

st.markdown(
    """
**v07-Schwerpunkt**

- Parser weiter verfeinert
- **strengere Paket-Erkennung**
- **Details/Eigenschaften** bleiben sichtbar
- pro Paket wird standardmäßig die **letzte aktive Version** verwendet
"""
)

with st.expander("Was v07 konzeptionell anders macht", expanded=False):
    st.markdown(
        """
Diese Version versucht, den *aktuellen* aktiven Stand der Pakete besser abzubilden.

Dafür gilt nun:
- PRISMA liest weiterhin den gesamten Aufenthalt ein
- **Abgesetzte** Einträge werden nicht angezeigt
- wenn dasselbe Paket im Aufenthalt mehrfach aktiv vorkommt, verwendet PRISMA standardmäßig die **letzte aktive Paketversion**
"""
    )

uploaded_file = st.file_uploader(
    "Pflegeplan als XLSX hochladen",
    type=["xlsx"],
)

if uploaded_file is None:
    st.info("Lade eine XLSX-Datei hoch, um die Analyse zu starten.")
    st.stop()

try:
    temp_path = save_uploaded_file_temporarily(uploaded_file)
    parsed_entries, parser_stats = parse_pflegeplan_xlsx_v07(temp_path)
    df_all = entries_to_dataframe(parsed_entries)
    df_visible = apply_filters(df_all)

except Exception as exc:
    st.error("Beim Einlesen oder Verarbeiten der Datei ist ein Fehler aufgetreten.")
    st.exception(exc)
    st.stop()

summary = build_summary(df_visible)

col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
col1.metric("Sichtbare Einträge", summary["gesamt"])
col2.metric("Pakete", summary["pakete"])
col3.metric("Leistungen", summary["leistungen"])
col4.metric("Details", summary["details"])
col5.metric("PMD", summary["pmd"])
col6.metric("Manuell", summary["manuell"])
col7.metric("Mit Zyklus", summary["mit_zyklus"])

st.divider()

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Übersicht", "Marker", "Tabellenansicht", "Baumansicht", "Rohdaten / Export"]
)

with tab1:
    st.subheader("Übersicht")

    left, right = st.columns([1, 1])

    with left:
        st.markdown("**Datei**")
        st.write(f"`{uploaded_file.name}`")
        st.write(f"Sichtbare Einträge: **{len(df_visible)}** von **{len(df_all)}** Parser-Einträgen")

    with right:
        st.markdown("**Verteilung der sichtbaren Einträge**")
        if not df_visible.empty:
            type_counts = df_visible["Typ"].value_counts().rename_axis("Typ").reset_index(name="Anzahl")
            st.dataframe(type_counts, use_container_width=True, hide_index=True)
        else:
            st.info("Keine Einträge in der aktuellen Ansicht.")

    with st.expander("Parser-Statistik", expanded=False):
        stats_df = pd.DataFrame(
            [
                {
                    "Kennzahl": key,
                    "Wert": json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value
                }
                for key, value in parser_stats.items()
            ]
        )
        st.dataframe(stats_df, use_container_width=True, hide_index=True)

with tab2:
    st.subheader("Marker für wichtige Pakete")
    marker_df = build_marker_table(df_all)
    st.dataframe(marker_df, use_container_width=True, hide_index=True)

with tab3:
    st.subheader("Tabellenansicht")

    display_columns = [
        "Titel-Zeile",
        "Status-Zeile",
        "Paket",
        "Herkunft",
        "Typ",
        "Eintrag",
        "Übergeordnete Leistung",
        "Zyklentext",
        "Zyklus-Typ",
        "Frequenz/Tag",
        "Intervall (Stunden)",
        "Uhrzeiten",
        "Paket-Vorkommen im Aufenthalt",
    ]

    if df_visible.empty:
        st.warning("Keine Daten für die aktuelle Ansicht vorhanden.")
    else:
        st.dataframe(
            df_visible[display_columns],
            use_container_width=True,
            hide_index=True,
        )

with tab4:
    st.subheader("Baumansicht")
    render_tree_view(df_visible)

with tab5:
    st.subheader("Rohdaten / Export")

    left, right = st.columns(2)

    with left:
        st.download_button(
            label="Sichtbare Ansicht als JSON herunterladen",
            data=dataframe_to_json_bytes(df_visible),
            file_name="prisma_v07_export_visible.json",
            mime="application/json",
        )

    with right:
        st.download_button(
            label="Sichtbare Ansicht als CSV herunterladen",
            data=dataframe_to_csv_bytes(df_visible),
            file_name="prisma_v07_export_visible.csv",
            mime="text/csv",
        )

    st.markdown("**Rohdaten-Vorschau**")
    if df_visible.empty:
        st.info("Keine Rohdaten sichtbar.")
    else:
        st.code(
            json.dumps(
                df_visible.head(25).to_dict(orient="records"),
                indent=2,
                ensure_ascii=False,
            ),
            language="json",
        )

st.divider()
st.success("PRISMA v07 geladen.")
