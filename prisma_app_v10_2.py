"""
PRISMA - App v10.2
==================

v10.2-Schwerpunkt:
- Grabber-TXT bleibt Standardimport
- Corpus-Auswertung mit Sortierliste für ZIPs / mehrere Grabber-Dateien
- unbekannte Leistungen sind KEINE Fehler, sondern Review-Einträge
- keine automatischen Fuzzy-/Ähnlichkeitsmatches
"""

from __future__ import annotations

import io
import json
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd
import streamlit as st

from prisma_parser_v10_2 import parse_pflegeplan_txt_v10_2
from engine.engine_v10_2 import run_engine_v10_2

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
LEP_RULES_PATH = DATA_DIR / "lep_rules_v10_2.json"
LEP_ALIASES_PATH = DATA_DIR / "lep_aliases_v10_2.json"
CLASSIFICATION_PATH = DATA_DIR / "entry_classification_v10_2.json"


# ============================================================
# ALLGEMEINE HILFSFUNKTIONEN
# ============================================================

@st.cache_data(show_spinner=False)
def load_classification() -> Dict[str, Any]:
    if not CLASSIFICATION_PATH.exists():
        return {"package_classes": {}, "fallbacks": {}}
    return json.loads(CLASSIFICATION_PATH.read_text(encoding="utf-8"))


def _safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value


def decode_bytes(data: bytes) -> str:
    """Dekodiert Grabber-Dateien robust."""
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def read_txt_files_from_zip(uploaded_zip) -> List[Dict[str, Any]]:
    """Liest alle .txt-Dateien aus einer ZIP rekursiv aus."""
    payload: List[Dict[str, Any]] = []
    raw_zip = uploaded_zip.getvalue()

    with zipfile.ZipFile(io.BytesIO(raw_zip), "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            if not info.filename.lower().endswith(".txt"):
                continue
            data = zf.read(info)
            payload.append(
                {
                    "source_name": Path(info.filename).name,
                    "source_path": info.filename,
                    "folder": str(Path(info.filename).parent),
                    "raw_text": decode_bytes(data),
                }
            )

    payload.sort(key=lambda x: x["source_path"])
    return payload


def get_package_class(package_name: str, package_raw: str, classification: Dict[str, Any]) -> Dict[str, str]:
    package_classes = classification.get("package_classes", {}) or {}
    fallbacks = classification.get("fallbacks", {}) or {}

    if package_name in package_classes:
        return package_classes[package_name]
    if package_raw in package_classes:
        return package_classes[package_raw]
    if "(PMD)" in str(package_raw):
        return fallbacks.get("pmd_package", {"class": "pmd_auto_package", "label": "PMD-/automatisch ausgeleitetes Paket"})
    return fallbacks.get("unknown_package", {"class": "unknown_or_needs_review", "label": "Ungeklärt / manuell zu prüfen"})


def get_service_class(row: Dict[str, Any], classification: Dict[str, Any]) -> Dict[str, str]:
    fallbacks = classification.get("fallbacks", {}) or {}
    lep_id = str(row.get("LEP-ID") or "")
    match_type = str(row.get("Match-Typ") or "")

    if not lep_id:
        return fallbacks.get("unmatched_service", {"class": "needs_manual_classification", "label": "Unbekannt / manuell zuordnen"})
    if lep_id.startswith("LOCAL_"):
        return fallbacks.get("local_known_service", {"class": "local_known", "label": "Lokal bekannte Leistung"})
    return fallbacks.get("lep_verified_service", {"class": "lep_verified", "label": "LEP-verifizierte Leistung"})

def classify_review_item(title: str, package: str, details: str = "", zyklentext: str = "") -> Dict[str, Any]:
    """
    Sortiert unbekannte Einträge in eine Review-Kategorie.

    WICHTIG:
    Diese Funktion erzeugt KEINEN Match und keine fachliche Gleichsetzung.
    Sie dient nur dazu, die manuelle Review-Liste lesbarer zu sortieren.
    """
    classification = load_classification()
    categories = classification.get("review_categories", {}) or {}

    title_clean = str(title or "").strip()
    title_lower = title_clean.lower()
    package_clean = str(package or "").strip()
    package_lower = package_clean.lower()
    details_clean = str(details or "").strip()
    zyklus_clean = str(zyklentext or "").strip()

    def cat(key: str, cause: str) -> Dict[str, Any]:
        info = categories.get(key, {})
        return {
            "Review-Kategorie": info.get("label", key),
            "Review-Klasse": key,
            "Vermutete Ursache": cause,
            "Review-Priorität": info.get("priority", "mittel"),
            "Prüffrage": info.get("review_question", "Manuell prüfen."),
            "Manuelle Entscheidung": "",
            "Team-Kommentar": "",
            "Auto-Match erlaubt": False,
        }

    # Detail-/Eigenschaftskandidaten: kein automatischer Match, nur Review-Sortierung.
    detail_markers = [
        "..", ":", "[", "]",
        "pvk", "zvk", "picc", "piccline", "antibiotikum", "elektrolyte",
        "atemfrequenz", "puls", "blutdruck", "körpertemperatur",
        "wunde", "dekubitus", "prevena", "vac", "redon", "drainage",
        "beidseits", "rechts", "links", "antikoagulation"
    ]
    if not zyklus_clean and any(marker in title_lower for marker in detail_markers):
        return cat(
            "possible_detail_or_property",
            "Eintrag wirkt wie Eigenschaft/Detail, nicht zwingend wie eigenständige Leistung."
        )

    # PMD-Kontext: unbekannte Einträge in PMD-Paketen getrennt sichtbar machen.
    if re.match(r"^\d{1,2}\s+", package_clean):
        if "[" in title_clean or ":" in title_clean:
            return cat(
                "pmd_context_review",
                "Unbekannter Eintrag im PMD-Paket mit Problem-/Ausprägungsstruktur."
            )
        return cat(
            "pmd_context_review",
            "Unbekannter Eintrag liegt in einem PMD-Paket; fachliche Zuordnung prüfen."
        )

    # Hausinterne/organisatorische Standards.
    org_words = [
        "organisieren", "vor-/nachbereiten", "vorbereiten", "nachbereiten",
        "ein-/auspacken", "assessment", "anamnese", "gespräch",
        "identifikationsarmband", "bettplatz", "eintritt", "verlegung",
        "übernahmekontrolle", "antrittskontrolle", "beratung", "anleitung",
        "instruktion", "umgebung gestalten", "kleidung vor"
    ]
    if any(word in title_lower for word in org_words):
        return cat(
            "possible_house_internal_or_org_item",
            "Eintrag wirkt organisatorisch, hausintern oder standardbezogen."
        )

    # Strukturauffällig: kein Zyklus und keine Details bei mutmaßlicher Leistung.
    if not zyklus_clean and not details_clean:
        return cat(
            "structural_planning_review",
            "Unbekannter Eintrag ohne Zyklus und ohne Detailkontext; Planungsstruktur prüfen."
        )

    # Fachbereichsspezifische Pakete.
    specialty_packages = ["gas", "end", "der", "kar", "nph", "rht", "hae", "neu", "str"]
    if any(part in package_lower for part in specialty_packages):
        return cat(
            "specialty_specific_review",
            "Eintrag könnte fachbereichsspezifisch sein und braucht manuelle Klassifikation."
        )

    return cat(
        "needs_lep_or_local_classification",
        "Eigenständiger unbekannter Eintrag; LEP, lokal bekannte Leistung oder hausinterne Maßnahme prüfen."
    )


# ============================================================
# DATAFRAME-HELFER EINZELANALYSE
# ============================================================

def parser_entries_to_dataframe(entries: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    classification = load_classification()

    for entry in entries:
        zyklus_info = entry.get("zyklus_info", {}) or {}
        pkg_class = get_package_class(entry.get("package") or "", entry.get("package_raw") or "", classification)
        rows.append(
            {
                "Eintrag-ID": entry.get("entry_id"),
                "Parent-ID": entry.get("parent_entry_id"),
                "Titel-Zeile": entry.get("title_row"),
                "Status-Zeile": entry.get("status_row"),
                "Paket": entry.get("package"),
                "Paket-Kategorie": pkg_class.get("label"),
                "Paket-Klasse": pkg_class.get("class"),
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
    classification = load_classification()

    for entry in parsed_entries:
        if entry.entry_type != "leistung":
            continue
        lep_id = entry.matched.lep_id if entry.matched else ""
        row = {
            "Eintrag-ID": entry.entry_id,
            "Paket": entry.package,
            "Anzeige": entry.display_title,
            "Titel": entry.title,
            "Details": ", ".join(entry.details),
            "Zyklentext": entry.zyklentext,
            "LEP-ID": lep_id,
            "LEP-Titel": entry.matched.lep_title if entry.matched else "",
            "Match-Typ": entry.matched.match_type if entry.matched else "",
            "Confidence": entry.matched.confidence if entry.matched else "",
        }
        svc_class = get_service_class(row, classification)
        row["Leistungs-Kategorie"] = svc_class.get("label")
        row["Leistungs-Klasse"] = svc_class.get("class")
        rows.append(row)
    return pd.DataFrame(rows)


def unmatched_entries_to_dataframe(unmatched_entries: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in unmatched_entries:
        details = ", ".join(item.get("details", []))
        review = classify_review_item(
            title=item.get("title"),
            package=item.get("package"),
            details=details,
            zyklentext=item.get("zyklentext"),
        )
        rows.append(
            {
                "Eintrag-ID": item.get("entry_id"),
                "Paket": item.get("package"),
                "Anzeige": item.get("display_title"),
                "Titel": item.get("title"),
                "Details": details,
                "Zyklentext": item.get("zyklentext"),
                "Review-Status": "needs_manual_classification",
                **review,
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


def render_metadata(parser_stats: Dict[str, Any]) -> None:
    metadata = parser_stats.get("metadata", {}) or {}
    if not metadata:
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pfleg OE", metadata.get("Pfleg OE", ""))
    c2.metric("Fachabteilung", metadata.get("Fachabt.", ""))
    c3.metric("Startdatum", metadata.get("Startdat", ""))
    c4.metric("Enddatum", metadata.get("Endedat.", ""))


def run_single_analysis(raw_text: str, source_name: str) -> Dict[str, Any]:
    parser_entries, parser_stats = parse_pflegeplan_txt_v10_2(raw_text, source_name=source_name)
    engine_result = run_engine_v10_2(parser_entries, LEP_RULES_PATH, LEP_ALIASES_PATH)
    return {
        "parser_entries": parser_entries,
        "parser_stats": parser_stats,
        "engine_result": engine_result,
    }


# ============================================================
# CORPUS-ANALYSE
# ============================================================

def analyse_corpus(files: List[Dict[str, Any]]) -> Dict[str, pd.DataFrame]:
    classification = load_classification()

    file_rows: List[Dict[str, Any]] = []
    package_rows: List[Dict[str, Any]] = []
    service_rows: List[Dict[str, Any]] = []
    unmatched_rows: List[Dict[str, Any]] = []
    finding_rows: List[Dict[str, Any]] = []
    warning_rows: List[Dict[str, Any]] = []

    for item in files:
        source_name = item["source_name"]
        source_path = item["source_path"]
        folder = item.get("folder", "")

        try:
            result = run_single_analysis(item["raw_text"], source_name=source_name)
            parser_entries = result["parser_entries"]
            parser_stats = result["parser_stats"]
            engine_result = result["engine_result"]
            metadata = parser_stats.get("metadata", {}) or {}
            match_summary = engine_result["match_summary"]
            rule_summary = engine_result["rule_summary"]

            file_rows.append(
                {
                    "Datei": source_name,
                    "Pfad": source_path,
                    "Ordner": folder,
                    "Pfleg OE": metadata.get("Pfleg OE", ""),
                    "Fachabteilung": metadata.get("Fachabt.", ""),
                    "Parser-Einträge": len(parser_entries),
                    "Pakete": sum(1 for e in parser_entries if e.get("row_type") == "paket"),
                    "Leistungen": match_summary.get("service_count", 0),
                    "Details": sum(1 for e in parser_entries if e.get("row_type") == "detail"),
                    "Gematcht": match_summary.get("matched_count", 0),
                    "Verifiziert": match_summary.get("verified_match_count", 0),
                    "Lokal bekannt": match_summary.get("local_match_count", 0),
                    "Unbekannt": match_summary.get("unmatched_count", 0),
                    "Match-Rate": match_summary.get("match_rate"),
                    "Regelbefunde": rule_summary.get("total_findings", 0),
                    "Warnungen": parser_stats.get("invalid_status_pairs", 0) + parser_stats.get("incomplete_pairs", 0),
                }
            )

            for entry in parser_entries:
                if entry.get("row_type") == "paket":
                    pkg_class = get_package_class(entry.get("package") or "", entry.get("package_raw") or "", classification)
                    package_rows.append(
                        {
                            "Datei": source_name,
                            "Pfad": source_path,
                            "Ordner": folder,
                            "Pfleg OE": metadata.get("Pfleg OE", ""),
                            "Fachabteilung": metadata.get("Fachabt.", ""),
                            "Paket": entry.get("package"),
                            "Paket roh": entry.get("package_raw"),
                            "Kategorie": pkg_class.get("label"),
                            "Klasse": pkg_class.get("class"),
                            "Herkunft": entry.get("entry_origin"),
                        }
                    )

            for entry in engine_result["parsed_entries"]:
                if entry.entry_type != "leistung":
                    continue
                lep_id = entry.matched.lep_id if entry.matched else ""
                match_type = entry.matched.match_type if entry.matched else ""
                tmp = {"LEP-ID": lep_id, "Match-Typ": match_type}
                svc_class = get_service_class(tmp, classification)
                service_rows.append(
                    {
                        "Datei": source_name,
                        "Pfad": source_path,
                        "Ordner": folder,
                        "Pfleg OE": metadata.get("Pfleg OE", ""),
                        "Fachabteilung": metadata.get("Fachabt.", ""),
                        "Paket": entry.package,
                        "Leistung": entry.title,
                        "Anzeige": entry.display_title,
                        "Details": ", ".join(entry.details),
                        "Zyklentext": entry.zyklentext,
                        "LEP-ID": lep_id,
                        "LEP-Titel": entry.matched.lep_title if entry.matched else "",
                        "Match-Typ": match_type,
                        "Kategorie": svc_class.get("label"),
                        "Klasse": svc_class.get("class"),
                    }
                )

            for unmatched in engine_result["unmatched_entries"]:
                details = ", ".join(unmatched.get("details", []))
                review = classify_review_item(
                    title=unmatched.get("title"),
                    package=unmatched.get("package"),
                    details=details,
                    zyklentext=unmatched.get("zyklentext"),
                )
                unmatched_rows.append(
                    {
                        "Datei": source_name,
                        "Pfad": source_path,
                        "Ordner": folder,
                        "Pfleg OE": metadata.get("Pfleg OE", ""),
                        "Fachabteilung": metadata.get("Fachabt.", ""),
                        "Paket": unmatched.get("package"),
                        "Leistung": unmatched.get("title"),
                        "Anzeige": unmatched.get("display_title"),
                        "Details": details,
                        "Zyklentext": unmatched.get("zyklentext"),
                        "Review-Status": "needs_manual_classification",
                        **review,
                    }
                )

            for finding in engine_result["findings"]:
                finding_rows.append(
                    {
                        "Datei": source_name,
                        "Pfad": source_path,
                        "Pfleg OE": metadata.get("Pfleg OE", ""),
                        "Fachabteilung": metadata.get("Fachabt.", ""),
                        "Finding-ID": finding.finding_id,
                        "Regeltyp": finding.rule_type,
                        "Schweregrad": finding.severity,
                        "Paket": finding.package,
                        "Primär-Eintrag": finding.title_primary,
                        "Meldung": finding.message,
                        "Empfehlung": finding.recommendation,
                    }
                )

            for skipped in parser_stats.get("skipped_invalid_status", []):
                warning_rows.append({"Datei": source_name, "Pfad": source_path, "Warnung": "invalid_status_pair", **skipped})
            for skipped in parser_stats.get("skipped_incomplete", []):
                warning_rows.append({"Datei": source_name, "Pfad": source_path, "Warnung": "incomplete_pair", **skipped})

        except Exception as exc:
            file_rows.append(
                {
                    "Datei": source_name,
                    "Pfad": source_path,
                    "Ordner": folder,
                    "Pfleg OE": "",
                    "Fachabteilung": "",
                    "Parser-Einträge": 0,
                    "Pakete": 0,
                    "Leistungen": 0,
                    "Details": 0,
                    "Gematcht": 0,
                    "Verifiziert": 0,
                    "Lokal bekannt": 0,
                    "Unbekannt": 0,
                    "Match-Rate": None,
                    "Regelbefunde": 0,
                    "Warnungen": 1,
                    "Fehler": str(exc),
                }
            )

    df_files = pd.DataFrame(file_rows)
    df_packages = pd.DataFrame(package_rows)
    df_services = pd.DataFrame(service_rows)
    df_unmatched = pd.DataFrame(unmatched_rows)
    df_findings = pd.DataFrame(finding_rows)
    df_warnings = pd.DataFrame(warning_rows)

    df_top_packages = build_frequency_table(df_packages, ["Paket", "Kategorie", "Klasse"])
    df_top_services = build_frequency_table(df_services, ["Leistung", "Paket", "Kategorie", "Klasse"])
    df_top_unmatched = build_frequency_table(
        df_unmatched,
        ["Leistung", "Paket", "Review-Kategorie", "Review-Priorität", "Vermutete Ursache", "Review-Status", "Auto-Match erlaubt"]
    )
    df_by_station = build_station_summary(df_files)

    return {
        "files": df_files,
        "packages": df_packages,
        "services": df_services,
        "unmatched": df_unmatched,
        "findings": df_findings,
        "warnings": df_warnings,
        "top_packages": df_top_packages,
        "top_services": df_top_services,
        "top_unmatched": df_top_unmatched,
        "by_station": df_by_station,
    }


def build_frequency_table(df: pd.DataFrame, group_cols: List[str]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=group_cols + ["Häufigkeit", "Dateien"])
    grouped = (
        df.groupby(group_cols, dropna=False)
        .agg(Häufigkeit=(group_cols[0], "size"), Dateien=("Datei", "nunique"))
        .reset_index()
        .sort_values(["Häufigkeit", "Dateien"], ascending=False)
    )
    return grouped


def build_station_summary(df_files: pd.DataFrame) -> pd.DataFrame:
    if df_files.empty:
        return pd.DataFrame()
    grouped = (
        df_files.groupby(["Pfleg OE", "Fachabteilung"], dropna=False)
        .agg(
            Pflegepläne=("Datei", "nunique"),
            Leistungen=("Leistungen", "sum"),
            Gematcht=("Gematcht", "sum"),
            Verifiziert=("Verifiziert", "sum"),
            Lokal_bekannt=("Lokal bekannt", "sum"),
            Unbekannt=("Unbekannt", "sum"),
            Parser_Warnungen=("Warnungen", "sum"),
            Regelbefunde=("Regelbefunde", "sum"),
        )
        .reset_index()
    )
    grouped["Match-Rate"] = grouped.apply(
        lambda r: round((r["Gematcht"] / r["Leistungen"]) * 100, 2) if r["Leistungen"] else None,
        axis=1,
    )
    return grouped.sort_values(["Pflegepläne", "Leistungen"], ascending=False)


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")


def make_export_zip(results: Dict[str, pd.DataFrame]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        export_names = {
            "files": "corpus_files.csv",
            "by_station": "corpus_by_station.csv",
            "top_packages": "corpus_top_packages.csv",
            "top_services": "corpus_top_services.csv",
            "top_unmatched": "corpus_top_unmatched_sortierliste.csv",
            "unmatched": "corpus_unmatched_detail_sortierliste.csv",
            "findings": "corpus_findings.csv",
            "warnings": "corpus_parser_warnings.csv",
        }
        for key, filename in export_names.items():
            df = results.get(key, pd.DataFrame())
            zf.writestr(filename, df.to_csv(index=False, sep=";", encoding="utf-8-sig"))
        manifest = {
            "version": "v10.2",
            "description": "Corpus-Sortierliste: unbekannte Einträge bleiben unbekannt und werden nicht automatisch gematcht.",
            "auto_similarity_matching_allowed": False,
            "unknown_is_error": False,
            "unknown_status": "needs_manual_classification",
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    buffer.seek(0)
    return buffer.getvalue()


# ============================================================
# UI
# ============================================================

st.set_page_config(page_title="PRISMA v10.2", page_icon="🔷", layout="wide")

st.title("🔷 PRISMA v10.2")
st.caption("Grabber-TXT + Corpus-Auswertung ohne automatische Ähnlichkeitsmatches")

with st.expander("Grundsatz für v10.2", expanded=False):
    st.markdown(
        """
- **Grabber-`.txt` bleibt der Standardimport**
- **Unbekannte Leistungen sind keine Fehler**, sondern Review-Einträge
- **Keine Fuzzy-/Ähnlichkeitsmatches**: ähnlich klingende Maßnahmen werden nicht automatisch zusammengeführt
- Corpus-Auswertung dient der Bestandsaufnahme und Priorisierung, nicht der automatischen fachlichen Gleichsetzung
        """
    )

single_tab, corpus_tab, config_tab = st.tabs(["Einzelplan", "Corpus-Analyse", "Klassifikation"])

with single_tab:
    st.subheader("Einzelplan-Analyse")
    uploaded_file = st.file_uploader("Pflegeplan aus Grabber als TXT hochladen", type=["txt"], key="single_txt")

    if uploaded_file is None:
        st.info("Lade eine Grabber-TXT-Datei hoch, um die Einzelanalyse zu starten.")
    else:
        raw_text = decode_bytes(uploaded_file.getvalue())
        result = run_single_analysis(raw_text, source_name=uploaded_file.name)
        parser_entries = result["parser_entries"]
        parser_stats = result["parser_stats"]
        engine_result = result["engine_result"]

        df_parser = parser_entries_to_dataframe(parser_entries)
        df_matches = matched_entries_to_dataframe(engine_result["parsed_entries"])
        df_unmatched = unmatched_entries_to_dataframe(engine_result["unmatched_entries"])
        df_findings = findings_to_dataframe(engine_result["findings"])

        match_summary = engine_result["match_summary"]
        rule_summary = engine_result["rule_summary"]

        render_metadata(parser_stats)
        st.divider()

        col1, col2, col3, col4, col5, col6 = st.columns(6)
        col1.metric("Parser-Einträge", len(df_parser))
        col2.metric("Gematchte Leistungen", match_summary["matched_count"])
        col3.metric("Verifizierte Matches", match_summary["verified_match_count"])
        col4.metric("Lokale Matches", match_summary["local_match_count"])
        col5.metric("Unbekannte Leistungen", match_summary["unmatched_count"])
        match_rate_display = "n/a" if match_summary["match_rate"] is None else f"{match_summary['match_rate']} %"
        col6.metric("Match-Rate", match_rate_display)

        if parser_stats.get("incomplete_pairs", 0) > 0 or parser_stats.get("invalid_status_pairs", 0) > 0:
            st.warning(
                f"Beim Import wurden {parser_stats.get('incomplete_pairs', 0)} unvollständige "
                f"und {parser_stats.get('invalid_status_pairs', 0)} ungültige Eintragspaare übersprungen."
            )

        tabs = st.tabs(["Parser", "Matches", "Review: unbekannt", "Regelbefunde", "Statistik"])
        with tabs[0]:
            st.dataframe(df_parser, use_container_width=True, hide_index=True)
        with tabs[1]:
            st.dataframe(df_matches, use_container_width=True, hide_index=True)
        with tabs[2]:
            if df_unmatched.empty:
                st.success("Keine unbekannten Leistungen vorhanden.")
            else:
                st.dataframe(df_unmatched, use_container_width=True, hide_index=True)
                st.download_button(
                    "Review-Liste als CSV herunterladen",
                    data=dataframe_to_csv_bytes(df_unmatched),
                    file_name="prisma_v10_2_unbekannte_leistungen_sortierliste.csv",
                    mime="text/csv",
                )
        with tabs[3]:
            if df_findings.empty:
                st.success("Keine Regelbefunde gefunden.")
            else:
                st.dataframe(df_findings, use_container_width=True, hide_index=True)
        with tabs[4]:
            stat_rows = []
            for key, value in parser_stats.items():
                stat_rows.append({"Bereich": "Parser", "Kennzahl": key, "Wert": _safe_json(value)})
            for key, value in match_summary.items():
                stat_rows.append({"Bereich": "Matching", "Kennzahl": key, "Wert": _safe_json(value)})
            for key, value in rule_summary.items():
                stat_rows.append({"Bereich": "Engine", "Kennzahl": key, "Wert": _safe_json(value)})
            st.dataframe(pd.DataFrame(stat_rows), use_container_width=True, hide_index=True)

with corpus_tab:
    st.subheader("Corpus-Analyse")
    st.markdown(
        """
Lade eine ZIP-Datei mit mehreren Grabber-`.txt`-Pflegeplänen hoch.  
PRISMA wertet den Bestand beschreibend aus und erstellt Review-Listen für unbekannte Leistungen.
        """
    )
    uploaded_zip = st.file_uploader("ZIP mit Grabber-TXT-Dateien hochladen", type=["zip"], key="corpus_zip")

    if uploaded_zip is None:
        st.info("Lade eine ZIP-Datei hoch, um die Corpus-Analyse zu starten.")
    else:
        with st.spinner("Corpus wird verarbeitet..."):
            files = read_txt_files_from_zip(uploaded_zip)
            results = analyse_corpus(files)

        df_files = results["files"]
        df_by_station = results["by_station"]
        df_top_packages = results["top_packages"]
        df_top_services = results["top_services"]
        df_top_unmatched = results["top_unmatched"]
        df_unmatched = results["unmatched"]
        df_findings = results["findings"]
        df_warnings = results["warnings"]

        total_files = len(df_files)
        total_services = int(df_files["Leistungen"].sum()) if not df_files.empty else 0
        total_matched = int(df_files["Gematcht"].sum()) if not df_files.empty else 0
        total_unknown = int(df_files["Unbekannt"].sum()) if not df_files.empty else 0
        total_verified = int(df_files["Verifiziert"].sum()) if not df_files.empty else 0
        total_local = int(df_files["Lokal bekannt"].sum()) if not df_files.empty else 0
        corpus_match_rate = round((total_matched / total_services) * 100, 2) if total_services else None

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Dateien", total_files)
        c2.metric("Leistungen", total_services)
        c3.metric("Gematcht", total_matched)
        c4.metric("Verifiziert", total_verified)
        c5.metric("Lokal bekannt", total_local)
        c6.metric("Unbekannt", total_unknown)
        st.metric("Corpus-Match-Rate", "n/a" if corpus_match_rate is None else f"{corpus_match_rate} %")

        st.download_button(
            "Corpus-Exporte als ZIP herunterladen",
            data=make_export_zip(results),
            file_name="prisma_v10_2_corpus_exports.zip",
            mime="application/zip",
        )

        corpus_tabs = st.tabs([
            "Dateien",
            "Nach Station/Abteilung",
            "Top-Pakete",
            "Top-Leistungen",
            "Review: unbekannt",
            "Regelbefunde",
            "Parser-Warnungen",
        ])

        with corpus_tabs[0]:
            st.dataframe(df_files, use_container_width=True, hide_index=True)
        with corpus_tabs[1]:
            st.dataframe(df_by_station, use_container_width=True, hide_index=True)
        with corpus_tabs[2]:
            st.dataframe(df_top_packages, use_container_width=True, hide_index=True)
        with corpus_tabs[3]:
            st.dataframe(df_top_services, use_container_width=True, hide_index=True)
        with corpus_tabs[4]:
            st.markdown("Unbekannte Leistungen werden **nicht** automatisch gematcht. Diese Liste ist eine manuelle **Sortier-/Reviewliste** mit vermuteter Ursache, Prüffrage und Priorität.")
            st.dataframe(df_top_unmatched, use_container_width=True, hide_index=True)
            st.download_button(
                "Top-Unbekannte als CSV herunterladen",
                data=dataframe_to_csv_bytes(df_top_unmatched),
                file_name="prisma_v10_2_top_unbekannte_sortierliste.csv",
                mime="text/csv",
            )
            with st.expander("Detailansicht aller unbekannten Leistungen", expanded=False):
                st.dataframe(df_unmatched, use_container_width=True, hide_index=True)
        with corpus_tabs[5]:
            st.dataframe(df_findings, use_container_width=True, hide_index=True)
        with corpus_tabs[6]:
            if df_warnings.empty:
                st.success("Keine Parser-Warnungen im Corpus.")
            else:
                st.dataframe(df_warnings, use_container_width=True, hide_index=True)

with config_tab:
    st.subheader("Klassifikation und Projektregeln")
    classification = load_classification()
    st.markdown(
        """
Diese Klassifikation ist bewusst vorläufig und kann später mit dem Team fachlich umbenannt oder erweitert werden.
        """
    )
    rules = classification.get("rules", {})
    st.write("**Projektregeln**")
    st.json(rules)

    pkg_rows = []
    for package, info in (classification.get("package_classes", {}) or {}).items():
        pkg_rows.append({"Paket": package, "Klasse": info.get("class"), "Kategorie": info.get("label"), "Notiz": info.get("notes", "")})
    st.write("**Paketklassifikation**")
    st.dataframe(pd.DataFrame(pkg_rows), use_container_width=True, hide_index=True)

    review_rows = []
    for key, info in (classification.get("review_categories", {}) or {}).items():
        review_rows.append(
            {
                "Review-Klasse": key,
                "Kategorie": info.get("label"),
                "Priorität": info.get("priority"),
                "Prüffrage": info.get("review_question"),
            }
        )
    st.write("**Review-/Sortierkategorien für unbekannte Einträge**")
    st.dataframe(pd.DataFrame(review_rows), use_container_width=True, hide_index=True)

st.divider()
st.success("PRISMA v10.2 geladen.")
