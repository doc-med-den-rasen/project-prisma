"""
PRISMA - Streamlit App
======================

Diese Version unterstützt zwei Eingabewege:

1. Pflegeplan als .xlsx hochladen
2. Pflegeplan direkt als Text einfügen

Wichtige Änderung:
- Parameter/Zusätze werden getrennt von tatsächlich geplanten Leistungen
  behandelt und standardmäßig ausgeblendet.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from prisma_v2_fixed import parse_pflegeplan_text, parse_pflegeplan_xlsx


# ============================================================
# STREAMLIT - GRUNDKONFIGURATION
# ============================================================

st.set_page_config(
    page_title="PRISMA",
    page_icon="🔷",
    layout="wide",
)


# ============================================================
# HILFSFUNKTIONEN - DATENUMWANDLUNG
# ============================================================

def entries_to_dataframe(entries: List[Dict[str, Any]]) -> pd.DataFrame:
    """Wandelt die Parser-Ausgabe in eine DataFrame-Struktur um."""
    rows = []

    for entry in entries:
        zyklus_info = entry.get("zyklus_info", {}) or {}

        rows.append(
            {
                "Zeile": entry.get("row_index"),
                "Quelle": entry.get("source_mode"),
                "Paket": entry.get("package"),
                "Paket (roh)": entry.get("package_raw"),
                "Herkunft": entry.get("entry_origin"),
                "Paket ist PMD": entry.get("package_is_pmd"),
                "Typ": entry.get("row_type"),
                "Ist geplantes Element": entry.get("is_planned_item"),
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
            }
        )

    df = pd.DataFrame(rows)

    if not df.empty:
        df["Hat Zyklentext"] = df["Zyklentext"].fillna("").astype(str).str.strip().ne("")

    return df


def build_summary(df: pd.DataFrame) -> Dict[str, int]:
    """Erzeugt Kennzahlen für die Übersichtskacheln."""
    if df.empty:
        return {
            "gesamt": 0,
            "geplant": 0,
            "pakete": 0,
            "leistungen": 0,
            "parameter": 0,
            "pmd": 0,
            "manuell": 0,
            "mit_zyklus": 0,
        }

    return {
        "gesamt": int(len(df)),
        "geplant": int(df["Ist geplantes Element"].sum()),
        "pakete": int((df["Typ"] == "paket").sum()),
        "leistungen": int((df["Typ"] == "leistung").sum()),
        "parameter": int((df["Typ"] == "parameter").sum()),
        "pmd": int((df["Herkunft"] == "PMD").sum()),
        "manuell": int((df["Herkunft"] == "manuell").sum()),
        "mit_zyklus": int(df["Hat Zyklentext"].sum()) if "Hat Zyklentext" in df.columns else 0,
    }


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")


def dataframe_to_json_bytes(df: pd.DataFrame) -> bytes:
    payload = df.to_dict(orient="records")
    return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")


def save_uploaded_file_temporarily(uploaded_file) -> Path:
    """Speichert eine hochgeladene Datei temporär ab."""
    suffix = Path(uploaded_file.name).suffix or ".xlsx"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getbuffer())
        return Path(tmp.name)


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Sidebar-Filter für die aktuelle Ansicht."""
    st.sidebar.header("Filter")

    if df.empty:
        return df

    default_types = ["paket", "leistung"]

    typ_options = ["paket", "leistung", "parameter"]
    selected_types = st.sidebar.multiselect(
        "Eintragstyp",
        options=typ_options,
        default=default_types,
        help="Parameter sind meist Zusätze/Unterbezeichner und keine eigenständig geplanten Leistungen.",
    )

    herkunft_options = sorted(df["Herkunft"].dropna().unique().tolist())
    selected_origin = st.sidebar.multiselect(
        "Herkunft",
        options=herkunft_options,
        default=herkunft_options,
        help="Unterscheidung zwischen PMD und manuellen Paketen.",
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

    zyklus_kinds = sorted([z for z in df["Zyklus-Typ"].dropna().unique().tolist() if str(z).strip()])
    selected_zyklus_kinds = st.sidebar.multiselect(
        "Zyklus-Typ",
        options=zyklus_kinds,
        default=zyklus_kinds,
    )

    only_planned_items = st.sidebar.checkbox(
        "Nur tatsächlich geplante Elemente",
        value=True,
        help="Blendet Parameter/Zusätze aus, selbst wenn sie im Export enthalten sind.",
    )

    search_term = st.sidebar.text_input(
        "Suche",
        placeholder="z. B. Mobilisation, Insulin, Atem...",
    ).strip()

    filtered = df.copy()

    # Zusätzlicher Sicherheitsfilter:
    # falls doch einmal Abgesetzt-Zeilen durch den Parser rutschen,
    # werden sie in der Oberfläche trotzdem ausgeblendet.
    if "Status" in filtered.columns:
        filtered = filtered[~filtered["Status"].fillna("").str.lower().str.contains("abgesetzt")]

    if selected_types:
        filtered = filtered[filtered["Typ"].isin(selected_types)]

    if selected_origin:
        filtered = filtered[filtered["Herkunft"].isin(selected_origin)]

    if selected_packages:
        filtered = filtered[filtered["Paket"].fillna("").isin(selected_packages)]

    if only_with_zyklus:
        filtered = filtered[filtered["Hat Zyklentext"] == True]

    if zyklus_kinds and len(selected_zyklus_kinds) != len(zyklus_kinds):
        filtered = filtered[filtered["Zyklus-Typ"].fillna("").isin(selected_zyklus_kinds)]

    if only_planned_items:
        filtered = filtered[filtered["Ist geplantes Element"] == True]

    if search_term:
        mask = (
            filtered["Eintrag"].fillna("").str.contains(search_term, case=False, na=False)
            | filtered["Paket"].fillna("").str.contains(search_term, case=False, na=False)
            | filtered["Zyklentext"].fillna("").str.contains(search_term, case=False, na=False)
        )
        filtered = filtered[mask]

    return filtered


def render_tree_view(df: pd.DataFrame) -> None:
    """
    Stellt den Pflegeplan gruppiert nach Paket dar:
        Paket
          └─ Leistung
               └─ Parameter
    """
    if df.empty:
        st.info("Keine Einträge für die Baumansicht vorhanden.")
        return

    pakete_df = df[df["Typ"] == "paket"].copy()

    if pakete_df.empty:
        st.warning("Es wurden in der aktuellen Filterung keine Pakete gefunden.")
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
                st.caption("Keine aktiven Leistungen in diesem Paket gefunden.")
                continue

            for _, leistung_row in leistungen.iterrows():
                leistung_name = str(leistung_row["Eintrag"])
                zyklus = str(leistung_row["Zyklentext"] or "").strip()

                if zyklus:
                    st.markdown(f"- **{leistung_name}**  \n  Zyklus: `{zyklus}`")
                else:
                    st.markdown(f"- **{leistung_name}**")

                parameter = df[
                    (df["Paket"] == paket_clean) &
                    (df["Typ"] == "parameter") &
                    (df["Übergeordnete Leistung"] == leistung_name)
                ].copy()

                for _, param_row in parameter.iterrows():
                    param_name = str(param_row["Eintrag"])
                    st.caption(f"Parameter/Zusatz: {param_name}")


# ============================================================
# HAUPT-UI
# ============================================================

st.title("🔷 PRISMA")
st.caption("Pflegeplan-Regelwerk zur Interventions-, Struktur- und Mapping-Analyse")

st.markdown(
    """
Diese Version von PRISMA hat jetzt zwei wichtige Änderungen:

1. **Pflegeplan direkt einfügen** statt zwingend .xlsx bauen zu müssen  
2. **Unterparameter/Zusätze** werden nicht mehr automatisch wie echte geplante Leistungen behandelt
"""
)

with st.expander("Was sich fachlich geändert hat", expanded=False):
    st.markdown(
        """
**Neu**
- Eingabe per **Textfenster**
- alternativ weiter per **.xlsx-Upload**
- Ebene 6 wird als **Parameter/Zusatz** behandelt
- Parameter sind standardmäßig **ausgeblendet**
- Schalter **\"Nur tatsächlich geplante Elemente\"** ist standardmäßig aktiv

**Wichtig**
- Text-Eingabe funktioniert am besten, wenn du den Pflegeplan tabellarisch aus dem KIS kopierst
- die feinste Hierarchie ist beim **.xlsx-Export** meist zuverlässiger
- falls das KIS beim Copy/Paste eine eigene Struktur liefert, können wir den Textparser danach noch gezielt schärfen
"""
    )

input_mode = st.radio(
    "Eingabemodus",
    options=["Text einfügen", "XLSX hochladen"],
    horizontal=True,
)

parsed_entries: List[Dict[str, Any]] = []
source_label = ""

if input_mode == "Text einfügen":
    st.subheader("Pflegeplan direkt einfügen")
    pasted_text = st.text_area(
        "Kopiere den anonymisierten Pflegeplan hier hinein",
        height=320,
        placeholder=(
            "Am besten direkt tabellarisch aus dem KIS kopieren und hier einfügen.\n"
            "PRISMA versucht Status, Zyklentext und Struktur automatisch zu erkennen."
        ),
    )

    if st.button("Eingefügten Text analysieren", type="primary"):
        try:
            parsed_entries = parse_pflegeplan_text(pasted_text)
            source_label = "Text-Eingabe"
            st.session_state["prisma_entries"] = parsed_entries
            st.session_state["prisma_source_label"] = source_label
        except Exception as exc:
            st.error("Beim Verarbeiten des eingefügten Texts ist ein Fehler aufgetreten.")
            st.exception(exc)

elif input_mode == "XLSX hochladen":
    st.subheader("Pflegeplan als Excel-Datei laden")
    uploaded_file = st.file_uploader(
        "Pflegeplan als .xlsx hochladen",
        type=["xlsx"],
        help="Bitte den exportierten Pflegeplan aus dem KIS als Excel-Datei hochladen.",
    )

    if uploaded_file is not None:
        try:
            temp_path = save_uploaded_file_temporarily(uploaded_file)
            parsed_entries = parse_pflegeplan_xlsx(temp_path)
            source_label = uploaded_file.name
            st.session_state["prisma_entries"] = parsed_entries
            st.session_state["prisma_source_label"] = source_label
        except Exception as exc:
            st.error("Beim Einlesen oder Verarbeiten der Datei ist ein Fehler aufgetreten.")
            st.exception(exc)

if "prisma_entries" not in st.session_state:
    st.info("Füge einen Pflegeplan ein oder lade eine .xlsx-Datei hoch, um die Analyse zu starten.")
    st.stop()

df = entries_to_dataframe(st.session_state["prisma_entries"])
source_label = st.session_state.get("prisma_source_label", "unbekannt")

summary = build_summary(df)

col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
col1.metric("Zeilen gesamt", summary["gesamt"])
col2.metric("Geplante Elemente", summary["geplant"])
col3.metric("Pakete", summary["pakete"])
col4.metric("Leistungen", summary["leistungen"])
col5.metric("Parameter", summary["parameter"])
col6.metric("PMD", summary["pmd"])
col7.metric("Mit Zyklus", summary["mit_zyklus"])

if summary["parameter"] > 0:
    st.info(
        f"PRISMA hat **{summary['parameter']} Parameter/Zusätze** erkannt. "
        "Diese werden getrennt von echten geplanten Leistungen behandelt und sind standardmäßig ausgeblendet."
    )

st.divider()

filtered_df = apply_filters(df)

tab1, tab2, tab3, tab4 = st.tabs(
    [
        "Übersicht",
        "Tabellenansicht",
        "Baumansicht",
        "Rohdaten / Export",
    ]
)

with tab1:
    st.subheader("Übersicht")

    left, right = st.columns([1, 1])

    with left:
        st.markdown("**Aktuelle Quelle**")
        st.write(f"Quelle: `{source_label}`")
        st.write(f"Sichtbare Einträge: **{len(filtered_df)}** von **{len(df)}**")

    with right:
        st.markdown("**Verteilung der sichtbaren Einträge**")
        if not filtered_df.empty:
            type_counts = filtered_df["Typ"].value_counts().rename_axis("Typ").reset_index(name="Anzahl")
            st.dataframe(type_counts, use_container_width=True, hide_index=True)
        else:
            st.info("Keine Einträge in der aktuellen Filterung.")

    st.markdown("**Einträge mit Zyklentext**")
    if not filtered_df.empty:
        zyklus_view = filtered_df[filtered_df["Hat Zyklentext"] == True][
            ["Paket", "Eintrag", "Typ", "Herkunft", "Zyklentext", "Zyklus-Typ"]
        ].copy()

        if zyklus_view.empty:
            st.info("Keine sichtbaren Einträge mit Zyklentext vorhanden.")
        else:
            st.dataframe(zyklus_view, use_container_width=True, hide_index=True)
    else:
        st.info("Keine Daten vorhanden.")

with tab2:
    st.subheader("Tabellenansicht")

    display_columns = [
        "Zeile",
        "Quelle",
        "Paket",
        "Herkunft",
        "Typ",
        "Ist geplantes Element",
        "Eintrag",
        "Übergeordnete Leistung",
        "Zyklentext",
        "Zyklus-Typ",
        "Frequenz/Tag",
        "Intervall (Stunden)",
        "Uhrzeiten",
    ]

    if filtered_df.empty:
        st.warning("Keine Daten für die aktuelle Filterung vorhanden.")
    else:
        st.dataframe(
            filtered_df[display_columns],
            use_container_width=True,
            hide_index=True,
        )

with tab3:
    st.subheader("Baumansicht")
    render_tree_view(filtered_df)

with tab4:
    st.subheader("Rohdaten / Export")

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("**JSON-Export der aktuellen Filterung**")
        st.download_button(
            label="Gefilterte Ansicht als JSON herunterladen",
            data=dataframe_to_json_bytes(filtered_df),
            file_name="prisma_export.json",
            mime="application/json",
        )

    with col_right:
        st.markdown("**CSV-Export der aktuellen Filterung**")
        st.download_button(
            label="Gefilterte Ansicht als CSV herunterladen",
            data=dataframe_to_csv_bytes(filtered_df),
            file_name="prisma_export.csv",
            mime="text/csv",
        )

    st.markdown("**Rohdaten-Vorschau**")
    if filtered_df.empty:
        st.info("Keine Rohdaten sichtbar.")
    else:
        st.code(
            json.dumps(
                filtered_df.head(25).to_dict(orient="records"),
                indent=2,
                ensure_ascii=False,
            ),
            language="json",
        )

st.divider()
st.success("PRISMA ist bereit für den nächsten Schritt. Als Nächstes kann die Regelprüfung andocken.")
