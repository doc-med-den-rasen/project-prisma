"""
PRISMA - Parser v10.2.1
===================

v10.2-Schwerpunkt:
- Standardimport aus Grabber-.txt-Dateien
- kein XLSX-Umweg mehr nötig
- robustes Einlesen des zweizeiligen Grabber-Formats
- unvollständige Schlusszeilen werden erkannt und übersprungen
- Ausgabe bleibt kompatibel zur bestehenden Engine v09.3
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ============================================================
# KONSTANTEN / REGELN
# ============================================================

MANUAL_PACKAGE_EXACT = {
    "tagesroutine",
    "aufnahme",
    "op vorbereitung",
    "op-vorbereitung",
    "geräte und hilfsmittel",
    "ppr 2.0 zusatzdaten",
    "eqs pneu",
    "verlegung",
    "überwachungen",
    "spezielle überwachungen",
}

MANUAL_PACKAGE_PATTERNS = [
    r"^(infusionen|vac|redon|perfusoren)\s+15/18/25$",
]

ACTION_MARKERS = [
    " durchführen",
    " unterstützen",
    " überwachen",
    " verabreichen",
    " wechseln",
    " zurechtmachen",
    " assistieren",
    " bereitstellen/abräumen",
    " führen",
    " messen",
    " leeren/wechseln",
    " reichen/entfernen",
    " anziehen",
    " ausziehen",
    " anlegen",
    " begleiten",
    " mobilisieren",
    " lagern",
    " kontrollieren",
    " versorgen",
    " vorbereiten",
    " vor-/nachbereiten",
    " punktieren",
    " absaugen",
    " planen",
    " organisieren",
    " erheben",
    " abnehmen",
    " berechnen",
    " entfernen",
    " ein-/auspacken",
    " nachbereiten",
    " überprüfen/warten",
    " beobachten",
]

VALID_STATUSES = {"aktiv", "abgesetzt"}


# ============================================================
# HILFSFUNKTIONEN
# ============================================================

def clean_text(value: Any) -> str:
    """Normalisiert Text, ohne fachliche Inhalte zu verändern."""
    if value is None:
        return ""
    text = str(value).replace("\xa0", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def strip_pmd_marker(title: str) -> str:
    """Entfernt '(PMD)' aus der Anzeige."""
    return re.sub(r"\s*\(PMD\)\s*$", "", clean_text(title), flags=re.IGNORECASE).strip()


def normalize_title_key(title: str) -> str:
    """Normalisiert einen Titel für Instanzzählung und Vergleiche."""
    return clean_text(title).lower()


def package_sort_key(package_name: str) -> tuple:
    """Sortiert PMD-Pakete numerisch, manuelle Pakete danach alphabetisch."""
    t = strip_pmd_marker(package_name)
    match = re.match(r"^(\d{1,2})\s+(.+)$", t)
    if match:
        return (0, int(match.group(1)), match.group(2).lower())
    return (1, 999, t.lower())


def parse_zyklentext(zyklentext: str) -> Dict[str, Any]:
    """Interpretiert häufige Zyklustexte in eine einfache Struktur."""
    text = clean_text(zyklentext)

    result: Dict[str, Any] = {
        "raw": text,
        "kind": None,
        "frequency_per_day": None,
        "times": [],
        "interval_hours": None,
        "notes": None,
    }

    if not text:
        return result

    lower = text.lower()

    if "bei bedarf" in lower:
        result["kind"] = "bei_bedarf"
        return result

    if lower.startswith("einmalig"):
        result["kind"] = "einmalig"
        result["notes"] = text
        return result

    match = re.search(r"(\d+)x\s*(?:tgl\.|pro tag)", lower)
    if match:
        result["kind"] = "mehrfach_pro_tag"
        result["frequency_per_day"] = int(match.group(1))
        result["times"] = re.findall(r"\b\d{1,2}:\d{2}\b", text)
        if not result["times"]:
            result["notes"] = text
        return result

    match = re.search(r"alle\s+(\d+)\s+stunden", lower)
    if match:
        result["kind"] = "stundenintervall"
        result["interval_hours"] = int(match.group(1))
        result["notes"] = text
        return result

    if lower.startswith("zyklus für die eqs-erfassung"):
        result["kind"] = "sonderzyklus"
        result["notes"] = text
        return result

    result["kind"] = "frei_text"
    result["notes"] = text
    return result


def is_package_title(title: str) -> bool:
    """Erkennt Paketzeilen bewusst streng."""
    t = clean_text(title)
    tl = t.lower()

    if not t:
        return False

    if "(pmd)" in tl:
        return True

    if tl in MANUAL_PACKAGE_EXACT:
        return True

    if tl.startswith("eqs "):
        return True

    return any(re.match(pattern, tl) for pattern in MANUAL_PACKAGE_PATTERNS)


def is_action_title(title: str) -> bool:
    """Erkennt typische Leistungs-/Aktionsformulierungen."""
    t = clean_text(title).lower()

    if not t:
        return False

    if any(marker.strip() in t for marker in ACTION_MARKERS):
        return True

    if t.startswith("visite "):
        return True

    if t.startswith("nächtlicher rundgang"):
        return True

    return False


def _next_id(counter: dict[str, int]) -> str:
    """Vergibt fortlaufende interne Eintrags-IDs."""
    counter["value"] += 1
    return f"E{counter['value']:05d}"


# ============================================================
# METADATEN / HEADER
# ============================================================

def _split_tab_fields(line: str) -> list[str]:
    """Splittet eine Grabber-Zeile tab-stabil."""
    return [part.strip() for part in line.split("\t")]


def _parse_labeled_fields(line: str) -> dict[str, str]:
    """
    Liest Zeilen wie:
    'Pfleg OE: 00000015,\tFachabt.: THG,\tAnlegeDat.: ...'
    """
    fields: dict[str, str] = {}
    for part in _split_tab_fields(line):
        part = part.strip().rstrip(",")
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        fields[clean_text(key)] = clean_text(value).rstrip(",")
    return fields


def extract_metadata(lines: list[str]) -> dict[str, str]:
    """Extrahiert unkritische technische Metadaten aus dem Grabber-Kopf."""
    metadata: dict[str, str] = {}

    for line in lines[:12]:
        raw = line.strip()

        if raw.startswith("Systembenutzer:"):
            fields = _parse_labeled_fields(raw)
            metadata.update(
                {
                    "Systemdatum": fields.get("Systemdatum", ""),
                    "Systemzeit": fields.get("Systemzeit", ""),
                }
            )

        if raw.startswith("Pfleg OE:"):
            fields = _parse_labeled_fields(raw)
            metadata.update(
                {
                    "Pfleg OE": fields.get("Pfleg OE", ""),
                    "Fachabt.": fields.get("Fachabt.", ""),
                    "AnlegeDat.": fields.get("AnlegeDat.", ""),
                    "Startdat": fields.get("Startdat", ""),
                    "Endedat.": fields.get("Endedat.", ""),
                }
            )

    return metadata


def detect_header_line(lines: list[str]) -> Optional[int]:
    """
    Liefert den 1-basierten Index der Tabellenkopfzeile.
    """
    for idx, line in enumerate(lines, start=1):
        normalized = clean_text(line).lower()
        if normalized.startswith("bezeichnung pflegeplaneintrag") and "status" in normalized:
            return idx
    return None


# ============================================================
# PAAR-EXTRAKTION AUS GRABBER-TXT
# ============================================================

def extract_logical_pairs_from_text(raw_text: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Liest das Grabber-TXT-Format ein:

    - Zeile N   = Titel
    - Zeile N+1 = Status / Zyklus / Metadaten als Tab-Zeile
    """
    lines = raw_text.splitlines()
    header_line = detect_header_line(lines)

    if header_line is None:
        raise ValueError("Keine Tabellenkopfzeile 'Bezeichnung Pflegeplaneintrag' gefunden.")

    logical_pairs: list[dict[str, Any]] = []
    skipped_incomplete: list[dict[str, Any]] = []
    skipped_invalid_status: list[dict[str, Any]] = []

    # Python-Index der ersten Datenzeile nach der Kopfzeile
    idx = header_line

    while idx < len(lines):
        title_raw = lines[idx]
        title = clean_text(title_raw)

        if not title:
            idx += 1
            continue

        if clean_text(title_raw).lower().startswith("bezeichnung pflegeplaneintrag"):
            idx += 1
            continue

        status_line_idx = idx + 1
        if status_line_idx >= len(lines):
            skipped_incomplete.append(
                {
                    "title_line": idx + 1,
                    "title": title,
                    "reason": "keine Statuszeile mehr vorhanden",
                }
            )
            break

        status_line = lines[status_line_idx]
        parts = _split_tab_fields(status_line)
        status = clean_text(parts[0]) if parts else ""
        status_lower = status.lower()

        if status_lower not in VALID_STATUSES:
            skipped_invalid_status.append(
                {
                    "title_line": idx + 1,
                    "status_line": status_line_idx + 1,
                    "title": title,
                    "raw_status_line": clean_text(status_line),
                    "reason": "Statuszeile nicht als Aktiv/Abgesetzt erkannt",
                }
            )
            idx += 2
            continue

        logical_pairs.append(
            {
                "title_row": idx + 1,
                "status_row": status_line_idx + 1,
                "title": title,
                "status": status,
                "evaluierung": clean_text(parts[1]) if len(parts) > 1 else "",
                "zyklentext": clean_text(parts[2]) if len(parts) > 2 else "",
                "anlegedat": clean_text(parts[3]) if len(parts) > 3 else "",
                "erfzeit": clean_text(parts[4]) if len(parts) > 4 else "",
                "angelegt_von": clean_text(parts[5]) if len(parts) > 5 else "",
            }
        )

        idx += 2

    info = {
        "header_line_detected": header_line,
        "raw_line_count": len(lines),
        "skipped_incomplete": skipped_incomplete,
        "skipped_invalid_status": skipped_invalid_status,
    }
    return logical_pairs, info


# ============================================================
# KERNPARSER
# ============================================================

def parse_pflegeplan_txt_v10_2(raw_text: str, source_name: str = "") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Parst einen Grabber-TXT-Pflegeplan und liefert:
    1. flache Eintragsliste für die App / Engine
    2. Parser-Statistik
    """
    logical_pairs, pair_info = extract_logical_pairs_from_text(raw_text)
    metadata = extract_metadata(raw_text.splitlines())

    active_pairs = [pair for pair in logical_pairs if pair["status"].lower() == "aktiv"]
    abgesetzt_pairs = [pair for pair in logical_pairs if "abgesetzt" in pair["status"].lower()]

    package_history_any: dict[str, int] = {}
    for pair in logical_pairs:
        if is_package_title(pair["title"]):
            key = strip_pmd_marker(pair["title"])
            package_history_any[key] = package_history_any.get(key, 0) + 1

    package_occurrences: list[dict[str, Any]] = []
    current_package: Optional[dict[str, Any]] = None
    current_action: Optional[dict[str, Any]] = None

    for pair in active_pairs:
        title = pair["title"]
        zyklus = pair["zyklentext"]

        if is_package_title(title):
            current_package = {
                "package": strip_pmd_marker(title),
                "package_raw": title,
                "is_pmd": "(pmd)" in title.lower(),
                "origin": "PMD" if "(pmd)" in title.lower() else "manuell",
                "title_row": pair["title_row"],
                "status_row": pair["status_row"],
                "package_details": [],
                "actions": [],
            }
            package_occurrences.append(current_package)
            current_action = None
            continue

        if current_package is None:
            current_package = {
                "package": "(ohne Paket)",
                "package_raw": "(ohne Paket)",
                "is_pmd": False,
                "origin": "manuell",
                "title_row": pair["title_row"],
                "status_row": pair["status_row"],
                "package_details": [],
                "actions": [],
            }
            package_occurrences.append(current_package)
            current_action = None

        if zyklus or is_action_title(title):
            current_action = {
                "title": title,
                "title_row": pair["title_row"],
                "status_row": pair["status_row"],
                "zyklentext": zyklus,
                "details": [],
                "title_key": normalize_title_key(title),
            }
            current_package["actions"].append(current_action)
        else:
            detail_obj = {
                "title": title,
                "title_row": pair["title_row"],
                "status_row": pair["status_row"],
            }

            if current_action is not None:
                current_action["details"].append(detail_obj)
            else:
                current_package["package_details"].append(detail_obj)

    latest_by_package: dict[str, dict[str, Any]] = {}
    for occurrence in package_occurrences:
        latest_by_package[occurrence["package"]] = occurrence

    kept_packages = list(latest_by_package.values())
    kept_packages.sort(key=lambda pkg: package_sort_key(pkg["package"]))

    entries: list[dict[str, Any]] = []
    id_counter = {"value": 0}

    for package_obj in kept_packages:
        package_name = package_obj["package"]
        package_raw = package_obj["package_raw"]
        package_id = _next_id(id_counter)

        counts_by_title: dict[str, int] = {}
        for action in package_obj["actions"]:
            counts_by_title[action["title_key"]] = counts_by_title.get(action["title_key"], 0) + 1

        seen_by_title: dict[str, int] = {}

        entries.append(
            {
                "entry_id": package_id,
                "parent_entry_id": None,
                "row_type": "paket",
                "title": package_raw,
                "display_title": package_raw,
                "package": package_name,
                "package_raw": package_raw,
                "parent_leistung": None,
                "parent_display": None,
                "zyklentext": "",
                "zyklus_info": parse_zyklentext(""),
                "package_is_pmd": package_obj["is_pmd"],
                "entry_origin": package_obj["origin"],
                "status": "Aktiv",
                "title_row": package_obj["title_row"],
                "status_row": package_obj["status_row"],
                "is_planned_core": True,
                "package_seen_anywhere_in_stay": package_history_any.get(package_name, 0) > 0,
                "package_occurrences_in_stay": package_history_any.get(package_name, 0),
                "instance_index": 1,
                "instance_total_same_title": 1,
            }
        )

        for package_detail in package_obj["package_details"]:
            entries.append(
                {
                    "entry_id": _next_id(id_counter),
                    "parent_entry_id": package_id,
                    "row_type": "detail",
                    "title": package_detail["title"],
                    "display_title": package_detail["title"],
                    "package": package_name,
                    "package_raw": package_raw,
                    "parent_leistung": None,
                    "parent_display": package_raw,
                    "zyklentext": "",
                    "zyklus_info": parse_zyklentext(""),
                    "package_is_pmd": package_obj["is_pmd"],
                    "entry_origin": package_obj["origin"],
                    "status": "Aktiv",
                    "title_row": package_detail["title_row"],
                    "status_row": package_detail["status_row"],
                    "is_planned_core": False,
                    "package_seen_anywhere_in_stay": package_history_any.get(package_name, 0) > 0,
                    "package_occurrences_in_stay": package_history_any.get(package_name, 0),
                    "instance_index": 1,
                    "instance_total_same_title": 1,
                }
            )

        for action in package_obj["actions"]:
            seen_by_title[action["title_key"]] = seen_by_title.get(action["title_key"], 0) + 1
            idx = seen_by_title[action["title_key"]]
            total = counts_by_title[action["title_key"]]

            display_title = action["title"]
            if total > 1:
                display_title = f"{action['title']} [{idx}/{total}]"

            action_id = _next_id(id_counter)

            entries.append(
                {
                    "entry_id": action_id,
                    "parent_entry_id": package_id,
                    "row_type": "leistung",
                    "title": action["title"],
                    "display_title": display_title,
                    "package": package_name,
                    "package_raw": package_raw,
                    "parent_leistung": None,
                    "parent_display": package_raw,
                    "zyklentext": action["zyklentext"],
                    "zyklus_info": parse_zyklentext(action["zyklentext"]),
                    "package_is_pmd": package_obj["is_pmd"],
                    "entry_origin": package_obj["origin"],
                    "status": "Aktiv",
                    "title_row": action["title_row"],
                    "status_row": action["status_row"],
                    "is_planned_core": True,
                    "package_seen_anywhere_in_stay": package_history_any.get(package_name, 0) > 0,
                    "package_occurrences_in_stay": package_history_any.get(package_name, 0),
                    "instance_index": idx,
                    "instance_total_same_title": total,
                }
            )

            for detail in action["details"]:
                entries.append(
                    {
                        "entry_id": _next_id(id_counter),
                        "parent_entry_id": action_id,
                        "row_type": "detail",
                        "title": detail["title"],
                        "display_title": detail["title"],
                        "package": package_name,
                        "package_raw": package_raw,
                        "parent_leistung": action["title"],
                        "parent_display": display_title,
                        "zyklentext": "",
                        "zyklus_info": parse_zyklentext(""),
                        "package_is_pmd": package_obj["is_pmd"],
                        "entry_origin": package_obj["origin"],
                        "status": "Aktiv",
                        "title_row": detail["title_row"],
                        "status_row": detail["status_row"],
                        "is_planned_core": False,
                        "package_seen_anywhere_in_stay": package_history_any.get(package_name, 0) > 0,
                        "package_occurrences_in_stay": package_history_any.get(package_name, 0),
                        "instance_index": idx,
                        "instance_total_same_title": total,
                    }
                )

    stats: dict[str, Any] = {
        "version": "v10.2",
        "source_format": "grabber_txt",
        "source_name": source_name,
        "header_line_detected": pair_info["header_line_detected"],
        "raw_line_count": pair_info["raw_line_count"],
        "logical_pairs_total": len(logical_pairs),
        "logical_pairs_aktiv": len(active_pairs),
        "logical_pairs_abgesetzt": len(abgesetzt_pairs),
        "invalid_status_pairs": len(pair_info["skipped_invalid_status"]),
        "incomplete_pairs": len(pair_info["skipped_incomplete"]),
        "package_occurrences_aktiv": len(package_occurrences),
        "unique_packages_kept_latest": len(kept_packages),
        "entries_output": len(entries),
        "package_history_any": package_history_any,
        "metadata": metadata,
        "skipped_invalid_status": pair_info["skipped_invalid_status"],
        "skipped_incomplete": pair_info["skipped_incomplete"],
        "format_note": "Grabber-TXT; Titel in Zeile N, Status/Zyklus in Zeile N+1; Details hängen an eindeutigen Leistungsinstanzen.",
    }

    return entries, stats


def parse_pflegeplan_txt_file_v10_2(txt_path: str | Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Komfortfunktion zum Parsen einer Grabber-TXT-Datei von der Platte."""
    path = Path(txt_path)
    raw_text = path.read_text(encoding="utf-8-sig")
    return parse_pflegeplan_txt_v10_2(raw_text, source_name=path.name)


def export_to_json(data: List[Dict[str, Any]], output_path: str | Path) -> None:
    """Speichert Einträge als JSON-Datei."""
    Path(output_path).write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    print("Dies ist der Grabber-TXT-Parser v10.2 von PRISMA.")
    print("Bitte starte die Streamlit-Oberfläche: prisma_app_v10.py")
