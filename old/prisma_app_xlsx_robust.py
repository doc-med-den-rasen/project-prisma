"""
PRISMA - XLSX-only Streamlit App (robust)
=========================================

Robustere Oberfläche für unterschiedliche XLSX-Varianten.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from prisma_xlsx_robust import parse_pflegeplan_xlsx


# ============================================================
# STREAMLIT-KONFIGURATION
# ============================================================

st.set_page_config(
    page_title="PRISMA",
    page_icon="🔷",
    layout="wide",
)


# ============================================================
# HILFSFUNKTIONEN
# ============================================================

def save_uploaded_file_temporarily(uploaded_file) -> Path:
    """Speichert eine hochgeladene XLSX-Datei temporär auf der Platte."""
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
                "Zeile": entry.get("row_index"),
                "Paket": entry.get("package"),
                "Paket (roh)": entry.get("package_raw"),
                "Herkunft": entry.get("entry_origin"),
                "Paket ist PMD": entry.get("package_is_pmd"),
                "Typ": entry.get("row_type"),
                "Eintrag": entry.get("title"),
                "Übergeordnete Leistung": entry.get("parent_leistung"),
                "Status": entry.get("status"),
                "Indent": entry.get("indent_level"),
                "Zyklentext": entry.get("zyklentext"),
                "Zyklus-Typ": zyklus_info.get("kind"),
                "Frequenz/Tag": zyklus_info.get("frequency_per_day"),
                "Intervall (Stunden)": zyklus_info.get("interval_hours"),
                "Uhrzeiten": ", ".join(zyklus_info.get("times", [])) if zyklus_info.get("times") else "",
                "Zyklus-Notiz": zyklus_info.get("notes"),
                "Geplantes Kernelement": entry.get("is_planned_core", False),
            }
        )

    df = pd.DataFrame(rows)

    if not df.empty:
        df["Hat Zyklentext"] = df["Zyklentext"].fillna("").astype(str).str.strip().ne("")
        df = df[~df["Status"].fillna("").str.lower().str.contains("abgesetzt")]

    return df


def build_summary(df: pd.DataFrame) -> Dict[str, int]:
    """Erzeugt Kennzahlen für die sichtbare Tabelle."""
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

    default_types = ["paket", "leistung"]
    available_types = [t for t in ["paket", "leistung", "detail"] if t in df["Typ"].dropna().unique().tolist()]
    selected_types = st.sidebar.multiselect(
        "Eintragstyp",
        options=available_types,
        default=[t for t in default_types if t in available_types],
        help="Details sind standardmäßig ausgeblendet, damit die Kernplanung klarer sichtbar bleibt.",
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
        placeholder="z. B. Mobilisation, Infusion, Atem...",
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
        )
        filtered = filtered[mask]

    return filtered


def render_tree_view(df: pd.DataFrame) -> None:
    """Stellt den Pflegeplan gruppiert nach Paket dar."""
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

        with st.expander(f"📦 {paket_name}  ·  Herkunft: {herkunft}", expanded=False):
            leistungen = df[
                (df["Paket"] == paket_clean) &
                (df["Typ"] == "leistung")
            ].copy()

            if leistungen.empty:
                st.caption("Keine sichtbaren Leistungen in diesem Paket.")
                continue

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
                    detail_name = str(detail_row["Eintrag"])
                    detail_zyklus = str(detail_row["Zyklentext"] or "").strip()

                    if detail_zyklus:
                        st.markdown(f"   - {detail_name}  \n     Zyklus: `{detail_zyklus}`")
                    else:
                        st.markdown(f"   - {detail_name}")


# ============================================================
# HAUPT-UI
# ============================================================

st.title("🔷 PRISMA")
st.caption("Pflegeplan-Regelwerk zur Interventions-, Struktur- und Mapping-Analyse")

st.markdown(
    """
Diese Version von PRISMA arbeitet **ausschließlich mit XLSX-Dateien**.

Verbessert in dieser Fassung:
- automatische Erkennung der Kopfzeile
- automatische Erkennung der Spalten
- robuster gegenüber Copy/Paste-XLSX
- **Abgesetzt** bleibt unsichtbar
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
    parsed_entries, parser_stats = parse_pflegeplan_xlsx(temp_path)
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

with st.expander("Parser-Statistik", expanded=False):
    stats_df = pd.DataFrame(
        [{"Kennzahl": key, "Wert": json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value}
         for key, value in parser_stats.items()]
    )
    st.dataframe(stats_df, use_container_width=True, hide_index=True)

st.divider()

tab1, tab2, tab3, tab4 = st.tabs(
    ["Übersicht", "Tabellenansicht", "Baumansicht", "Rohdaten / Export"]
)

with tab1:
    st.subheader("Übersicht")

    left, right = st.columns([1, 1])

    with left:
        st.markdown("**Datei**")
        st.write(f"`{uploaded_file.name}`")
        st.write(f"Sichtbare Einträge: **{len(df_visible)}** von **{len(df_all)}** aktiven Parser-Einträgen")

    with right:
        st.markdown("**Verteilung der sichtbaren Einträge**")
        if not df_visible.empty:
            type_counts = df_visible["Typ"].value_counts().rename_axis("Typ").reset_index(name="Anzahl")
            st.dataframe(type_counts, use_container_width=True, hide_index=True)
        else:
            st.info("Keine Einträge in der aktuellen Ansicht.")

    st.markdown("**Sichtbare Einträge mit Zyklentext**")
    zyklus_view = pd.DataFrame()
    if not df_visible.empty:
        zyklus_view = df_visible[df_visible["Hat Zyklentext"] == True][
            ["Paket", "Eintrag", "Typ", "Herkunft", "Zyklentext", "Zyklus-Typ"]
        ].copy()

    if zyklus_view.empty:
        st.info("Keine sichtbaren Einträge mit Zyklentext vorhanden.")
    else:
        st.dataframe(zyklus_view, use_container_width=True, hide_index=True)

with tab2:
    st.subheader("Tabellenansicht")

    display_columns = [
        "Zeile",
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
    ]

    if df_visible.empty:
        st.warning("Keine Daten für die aktuelle Ansicht vorhanden.")
    else:
        st.dataframe(
            df_visible[display_columns],
            use_container_width=True,
            hide_index=True,
        )

with tab3:
    st.subheader("Baumansicht")
    render_tree_view(df_visible)

with tab4:
    st.subheader("Rohdaten / Export")

    left, right = st.columns(2)

    with left:
        st.download_button(
            label="Sichtbare Ansicht als JSON herunterladen",
            data=dataframe_to_json_bytes(df_visible),
            file_name="prisma_export_visible.json",
            mime="application/json",
        )

    with right:
        st.download_button(
            label="Sichtbare Ansicht als CSV herunterladen",
            data=dataframe_to_csv_bytes(df_visible),
            file_name="prisma_export_visible.csv",
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
st.success("PRISMA XLSX-robust geladen.")
