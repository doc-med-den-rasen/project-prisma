"""
PRISMA - Engine v09
===================

Dieses Modul verbindet Parser-Ausgabe, Matching und die erste Regelprüfung.

Aktuell implementierte Regeln:
- duplicate_same_service
- included_redundancy
- excluded_but_separate_check
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .matcher_v09 import apply_matching
from .models_v09 import ParsedEntry, RuleFinding
from .rules_v09 import MESSAGES_V09, RULES_V09


def load_json(path: str | Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def build_parsed_entries(parser_entries: List[Dict[str, Any]]) -> List[ParsedEntry]:
    """
    Wandelt rohe Parser-Einträge in ParsedEntry-Objekte um.

    Zusätzlich werden Details an ihre jeweilige Eltern-Leistung gehängt,
    damit die Regel-Engine mit einem saubereren Kontext arbeiten kann.
    """
    id_to_details: Dict[str, List[str]] = defaultdict(list)
    for raw in parser_entries:
        if raw.get("row_type") == "detail":
            parent_id = raw.get("parent_entry_id")
            if parent_id:
                id_to_details[parent_id].append(raw.get("title", ""))

    parsed: List[ParsedEntry] = []
    for raw in parser_entries:
        if raw.get("row_type") == "detail":
            continue

        parsed.append(
            ParsedEntry(
                entry_id=raw.get("entry_id"),
                parent_entry_id=raw.get("parent_entry_id"),
                package=raw.get("package") or "",
                package_raw=raw.get("package_raw") or "",
                entry_type=raw.get("row_type") or "",
                title=raw.get("title") or "",
                display_title=raw.get("display_title") or raw.get("title") or "",
                details=id_to_details.get(raw.get("entry_id"), []),
                zyklentext=raw.get("zyklentext") or "",
                zyklus_info=raw.get("zyklus_info") or {},
                origin=raw.get("entry_origin") or "manuell",
                package_is_pmd=bool(raw.get("package_is_pmd")),
                title_row=raw.get("title_row"),
                status_row=raw.get("status_row"),
                instance_index=raw.get("instance_index") or 1,
                instance_total_same_title=raw.get("instance_total_same_title") or 1,
            )
        )
    return parsed


def make_signature(entry: ParsedEntry) -> Tuple[Any, ...]:
    """Baut eine Signatur für Dublettenprüfung."""
    matched_key = entry.matched.lep_id if entry.matched else None
    details_key = tuple(sorted(d.strip().lower() for d in entry.details))
    zyklus_key = (entry.zyklentext or "").strip().lower()
    return (
        entry.package,
        matched_key or entry.title.strip().lower(),
        details_key,
        zyklus_key,
    )


def _next_finding_id(counter: Dict[str, int]) -> str:
    counter["value"] += 1
    return f"F{counter['value']:05d}"


def check_duplicate_same_service(entries: List[ParsedEntry], counter: Dict[str, int]) -> List[RuleFinding]:
    findings: List[RuleFinding] = []
    if not RULES_V09["duplicate_same_service"]["enabled"]:
        return findings

    by_signature: Dict[Tuple[Any, ...], List[ParsedEntry]] = defaultdict(list)
    for entry in entries:
        if entry.entry_type != "leistung":
            continue
        by_signature[make_signature(entry)].append(entry)

    for group in by_signature.values():
        if len(group) < 2:
            continue
        anchor = group[0]
        for other in group[1:]:
            findings.append(
                RuleFinding(
                    finding_id=_next_finding_id(counter),
                    rule_type="duplicate_same_service",
                    severity=RULES_V09["duplicate_same_service"]["severity"],
                    package=anchor.package,
                    entry_id_primary=anchor.entry_id,
                    entry_id_secondary=other.entry_id,
                    title_primary=anchor.display_title,
                    title_secondary=other.display_title,
                    message=MESSAGES_V09["duplicate_same_service"].format(title=anchor.title),
                    confidence=0.95,
                    payload={
                        "zyklus_primary": anchor.zyklentext,
                        "zyklus_secondary": other.zyklentext,
                        "details_primary": anchor.details,
                        "details_secondary": other.details,
                    },
                )
            )
    return findings


def build_lep_lookup(lep_rule_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {entry["lep_id"]: entry for entry in lep_rule_data.get("entries", []) if entry.get("lep_id")}


def check_included_redundancy(entries: List[ParsedEntry], lep_rule_data: Dict[str, Any], counter: Dict[str, int]) -> List[RuleFinding]:
    findings: List[RuleFinding] = []
    if not RULES_V09["included_redundancy"]["enabled"]:
        return findings

    lep_lookup = build_lep_lookup(lep_rule_data)
    entries_by_package: Dict[str, List[ParsedEntry]] = defaultdict(list)
    for entry in entries:
        if entry.entry_type == "leistung" and entry.matched and entry.matched.lep_id:
            entries_by_package[entry.package].append(entry)

    for package_entries in entries_by_package.values():
        by_lep_id = {entry.matched.lep_id: entry for entry in package_entries if entry.matched and entry.matched.lep_id}
        for entry in package_entries:
            lep_rule = lep_lookup.get(entry.matched.lep_id)
            if not lep_rule:
                continue
            included_ids = [item.get("lep_id") for item in lep_rule.get("included", []) if item.get("lep_id")]
            for included_id in included_ids:
                child = by_lep_id.get(included_id)
                if not child or child.entry_id == entry.entry_id:
                    continue
                findings.append(
                    RuleFinding(
                        finding_id=_next_finding_id(counter),
                        rule_type="included_redundancy",
                        severity=RULES_V09["included_redundancy"]["severity"],
                        package=entry.package,
                        entry_id_primary=entry.entry_id,
                        entry_id_secondary=child.entry_id,
                        title_primary=entry.display_title,
                        title_secondary=child.display_title,
                        message=MESSAGES_V09["included_redundancy"].format(child=child.title, parent=entry.title),
                        confidence=0.9,
                        payload={
                            "parent_lep_id": entry.matched.lep_id,
                            "child_lep_id": included_id,
                        },
                    )
                )
    return findings


def check_excluded_but_separate_check(entries: List[ParsedEntry], lep_rule_data: Dict[str, Any], counter: Dict[str, int]) -> List[RuleFinding]:
    findings: List[RuleFinding] = []
    if not RULES_V09["excluded_but_separate_check"]["enabled"]:
        return findings

    lep_lookup = build_lep_lookup(lep_rule_data)
    entries_by_package: Dict[str, List[ParsedEntry]] = defaultdict(list)
    for entry in entries:
        if entry.entry_type == "leistung" and entry.matched and entry.matched.lep_id:
            entries_by_package[entry.package].append(entry)

    for package_entries in entries_by_package.values():
        lep_ids_present = {entry.matched.lep_id for entry in package_entries if entry.matched and entry.matched.lep_id}
        for entry in package_entries:
            lep_rule = lep_lookup.get(entry.matched.lep_id)
            if not lep_rule:
                continue
            for excluded in lep_rule.get("excluded", []):
                excluded_id = excluded.get("lep_id")
                excluded_title = excluded.get("title")
                if not excluded_id or excluded_id in lep_ids_present:
                    continue
                findings.append(
                    RuleFinding(
                        finding_id=_next_finding_id(counter),
                        rule_type="excluded_but_separate_check",
                        severity=RULES_V09["excluded_but_separate_check"]["severity"],
                        package=entry.package,
                        entry_id_primary=entry.entry_id,
                        entry_id_secondary=None,
                        title_primary=entry.display_title,
                        title_secondary=None,
                        message=MESSAGES_V09["excluded_but_separate_check"].format(excluded=excluded_title, parent=entry.title),
                        confidence=0.65,
                        payload={
                            "parent_lep_id": entry.matched.lep_id,
                            "excluded_lep_id": excluded_id,
                            "excluded_title": excluded_title,
                        },
                    )
                )
    return findings


def summarize_matches(entries: List[ParsedEntry]) -> Dict[str, Any]:
    total_services = sum(1 for entry in entries if entry.entry_type == "leistung")
    matched_services = sum(1 for entry in entries if entry.entry_type == "leistung" and entry.matched is not None)
    unmatched_services = total_services - matched_services
    return {
        "service_count": total_services,
        "matched_count": matched_services,
        "unmatched_count": unmatched_services,
        "match_rate": round((matched_services / total_services) * 100, 2) if total_services else 0.0,
    }


def run_engine_v09(parser_entries: List[Dict[str, Any]], lep_rules_path: str | Path, lep_aliases_path: str | Path) -> Dict[str, Any]:
    """Gesamte v09-Pipeline."""
    lep_rule_data = load_json(lep_rules_path)
    alias_data = load_json(lep_aliases_path)
    parsed_entries = build_parsed_entries(parser_entries)
    parsed_entries = apply_matching(parsed_entries, alias_data, lep_rule_data)

    counter = {"value": 0}
    findings: List[RuleFinding] = []
    findings.extend(check_duplicate_same_service(parsed_entries, counter))
    findings.extend(check_included_redundancy(parsed_entries, lep_rule_data, counter))
    findings.extend(check_excluded_but_separate_check(parsed_entries, lep_rule_data, counter))

    return {
        "parsed_entries": parsed_entries,
        "findings": findings,
        "match_summary": summarize_matches(parsed_entries),
        "rule_summary": {
            "total_findings": len(findings),
            "by_type": {
                "duplicate_same_service": sum(1 for f in findings if f.rule_type == "duplicate_same_service"),
                "included_redundancy": sum(1 for f in findings if f.rule_type == "included_redundancy"),
                "excluded_but_separate_check": sum(1 for f in findings if f.rule_type == "excluded_but_separate_check"),
            },
        },
    }
