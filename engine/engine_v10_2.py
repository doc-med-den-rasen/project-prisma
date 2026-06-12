
"""
PRISMA - Engine v10.2
=====================

v10.2:
- bündelt Regelbefunde pro Leistungsanker
- ergänzt lokale Alias-Matches für wiederkehrende Unmatched-Leistungen
- zeigt bei Plänen ohne Leistungszeilen die Match-Rate als n/a
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .matcher_v10_2 import apply_matching
from .models_v10_2 import ParsedEntry, RuleFinding
from .rules_v10_2 import MESSAGES_V10_2, RULES_V10_2


def load_json(path: str | Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def build_parsed_entries(parser_entries: List[Dict[str, Any]]) -> List[ParsedEntry]:
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
    matched_key = entry.matched.lep_id if entry.matched and entry.matched.lep_id else None
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


def build_lep_lookup(lep_rule_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {entry["lep_id"]: entry for entry in lep_rule_data.get("entries", []) if entry.get("lep_id")}


def _is_verified_lep_rule(lep_rule: Dict[str, Any]) -> bool:
    return not str(lep_rule.get("lep_id", "")).startswith("LOCAL_")


def check_duplicate_same_service(entries: List[ParsedEntry], counter: Dict[str, int]) -> List[RuleFinding]:
    findings: List[RuleFinding] = []
    if not RULES_V10_2["duplicate_same_service"]["enabled"]:
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
        findings.append(
            RuleFinding(
                finding_id=_next_finding_id(counter),
                rule_type="duplicate_same_service",
                severity=RULES_V10_2["duplicate_same_service"]["severity"],
                package=anchor.package,
                entry_id_primary=anchor.entry_id,
                entry_id_secondary=None,
                title_primary=anchor.display_title,
                title_secondary=None,
                message=MESSAGES_V10_2["duplicate_same_service"].format(title=anchor.title, count=len(group)),
                recommendation="Prüfen, ob diese Leistung nur einmal geplant werden sollte oder ob die Mehrfachplanung bewusst fachlich unterschiedlich ist.",
                confidence=0.95,
                payload={
                    "group_entry_ids": [e.entry_id for e in group],
                    "group_titles": [e.display_title for e in group],
                    "group_cycles": [e.zyklentext for e in group],
                    "group_details": [e.details for e in group],
                },
            )
        )
    return findings


def check_included_redundancy(entries: List[ParsedEntry], lep_rule_data: Dict[str, Any], counter: Dict[str, int]) -> List[RuleFinding]:
    findings: List[RuleFinding] = []
    if not RULES_V10_2["included_redundancy"]["enabled"]:
        return findings

    lep_lookup = build_lep_lookup(lep_rule_data)
    entries_by_package: Dict[str, List[ParsedEntry]] = defaultdict(list)
    for entry in entries:
        if entry.entry_type == "leistung" and entry.matched and entry.matched.lep_id:
            entries_by_package[entry.package].append(entry)

    for package_entries in entries_by_package.values():
        by_lep_id: Dict[str, List[ParsedEntry]] = defaultdict(list)
        for entry in package_entries:
            by_lep_id[entry.matched.lep_id].append(entry)

        for entry in package_entries:
            lep_rule = lep_lookup.get(entry.matched.lep_id)
            if not lep_rule or not _is_verified_lep_rule(lep_rule):
                continue
            children: List[ParsedEntry] = []
            included_ids = [item.get("lep_id") for item in lep_rule.get("included", []) if item.get("lep_id")]
            for included_id in included_ids:
                for child in by_lep_id.get(included_id, []):
                    if child.entry_id != entry.entry_id:
                        children.append(child)

            unique_children = []
            seen = set()
            for child in children:
                if child.entry_id not in seen:
                    seen.add(child.entry_id)
                    unique_children.append(child)

            if not unique_children:
                continue

            child_names = [child.display_title for child in unique_children]
            findings.append(
                RuleFinding(
                    finding_id=_next_finding_id(counter),
                    rule_type="included_redundancy",
                    severity=RULES_V10_2["included_redundancy"]["severity"],
                    package=entry.package,
                    entry_id_primary=entry.entry_id,
                    entry_id_secondary=None,
                    title_primary=entry.display_title,
                    title_secondary=None,
                    message=MESSAGES_V10_2["included_redundancy_grouped"].format(
                        parent=entry.title,
                        children=", ".join(child_names),
                    ),
                    recommendation=f'Prüfen, ob stattdessen die übergeordnete Leistung „{entry.title}“ als Hauptplanung ausreicht.',
                    confidence=0.9,
                    payload={
                        "parent_lep_id": entry.matched.lep_id,
                        "parent_title": entry.title,
                        "contained_entry_ids": [child.entry_id for child in unique_children],
                        "contained_titles": child_names,
                        "contained_lep_ids": [child.matched.lep_id for child in unique_children if child.matched],
                    },
                )
            )
    return findings


def check_excluded_but_separate_check(entries: List[ParsedEntry], lep_rule_data: Dict[str, Any], counter: Dict[str, int]) -> List[RuleFinding]:
    findings: List[RuleFinding] = []
    if not RULES_V10_2["excluded_but_separate_check"]["enabled"]:
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
            if not lep_rule or not _is_verified_lep_rule(lep_rule):
                continue

            missing_excluded = []
            for excluded in lep_rule.get("excluded", []):
                excluded_id = excluded.get("lep_id")
                excluded_title = excluded.get("title")
                if not excluded_id or excluded_id in lep_ids_present:
                    continue
                missing_excluded.append({"lep_id": excluded_id, "title": excluded_title})

            if not missing_excluded:
                continue

            findings.append(
                RuleFinding(
                    finding_id=_next_finding_id(counter),
                    rule_type="excluded_but_separate_check",
                    severity=RULES_V10_2["excluded_but_separate_check"]["severity"],
                    package=entry.package,
                    entry_id_primary=entry.entry_id,
                    entry_id_secondary=None,
                    title_primary=entry.display_title,
                    title_secondary=None,
                    message=MESSAGES_V10_2["excluded_but_separate_check_grouped"].format(
                        parent=entry.title,
                        excluded=", ".join(item["title"] for item in missing_excluded),
                    ),
                    recommendation="Bitte prüfen, welche dieser nicht enthaltenen Leistungen klinisch wirklich zusätzlich geplant werden sollten.",
                    confidence=0.65,
                    payload={
                        "parent_lep_id": entry.matched.lep_id,
                        "excluded_items": missing_excluded,
                    },
                )
            )
    return findings


def summarize_matches(entries: List[ParsedEntry]) -> Dict[str, Any]:
    services = [entry for entry in entries if entry.entry_type == "leistung"]
    matched = [entry for entry in services if entry.matched and entry.matched.lep_id]
    unmatched = [entry for entry in services if not entry.matched or not entry.matched.lep_id]
    local_matches = [entry for entry in matched if str(entry.matched.lep_id).startswith("LOCAL_")]
    verified_matches = [entry for entry in matched if not str(entry.matched.lep_id).startswith("LOCAL_")]

    unmatched_by_package = Counter(entry.package for entry in unmatched)
    match_by_package = defaultdict(lambda: {"matched": 0, "unmatched": 0})
    for entry in matched:
        match_by_package[entry.package]["matched"] += 1
    for entry in unmatched:
        match_by_package[entry.package]["unmatched"] += 1

    return {
        "service_count": len(services),
        "matched_count": len(matched),
        "verified_match_count": len(verified_matches),
        "local_match_count": len(local_matches),
        "unmatched_count": len(unmatched),
        "match_rate": round((len(matched) / len(services)) * 100, 2) if services else None,
        "unmatched_by_package": dict(unmatched_by_package),
        "match_by_package": dict(match_by_package),
    }


def collect_unmatched(entries: List[ParsedEntry]) -> List[Dict[str, Any]]:
    rows = []
    for entry in entries:
        if entry.entry_type != "leistung":
            continue
        if entry.matched and entry.matched.lep_id:
            continue
        suggestions = entry.matched.suggestions if entry.matched else []
        rows.append(
            {
                "entry_id": entry.entry_id,
                "package": entry.package,
                "display_title": entry.display_title,
                "title": entry.title,
                "details": entry.details,
                "zyklentext": entry.zyklentext,
                "suggestions": [
                    {
                        "lep_id": s.lep_id,
                        "lep_title": s.lep_title,
                        "score": s.score,
                        "suggestion_type": s.suggestion_type,
                    }
                    for s in suggestions
                ],
            }
        )
    return rows


def run_engine_v10_2(parser_entries: List[Dict[str, Any]], lep_rules_path: str | Path, lep_aliases_path: str | Path) -> Dict[str, Any]:
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
        "unmatched_entries": collect_unmatched(parsed_entries),
        "match_summary": summarize_matches(parsed_entries),
        "rule_summary": {
            "total_findings": len(findings),
            "by_type": {
                "duplicate_same_service": sum(1 for f in findings if f.rule_type == "duplicate_same_service"),
                "included_redundancy": sum(1 for f in findings if f.rule_type == "included_redundancy"),
                "excluded_but_separate_check": sum(1 for f in findings if f.rule_type == "excluded_but_separate_check"),
            },
            "by_severity": {
                "low": sum(1 for f in findings if f.severity == "low"),
                "medium": sum(1 for f in findings if f.severity == "medium"),
                "high": sum(1 for f in findings if f.severity == "high"),
            },
        },
    }
