"""
PRISMA - Engine v09.2
=====================

v09.2 fokussiert auf bessere Match-Quote.
Die Included/Excluded-Logik ist am stärksten für verifizierte LEP-Einträge.
Lokale provisorische Titel-Matches helfen vor allem bei Dubletten und Transparenz.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .matcher_v09_2 import apply_matching
from .models_v09_2 import ParsedEntry, RuleFinding
from .rules_v09_2 import MESSAGES_V09_2, RULES_V09_2


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


def check_duplicate_same_service(entries: List[ParsedEntry], counter: Dict[str, int]) -> List[RuleFinding]:
    findings: List[RuleFinding] = []
    if not RULES_V09_2["duplicate_same_service"]["enabled"]:
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
                    severity=RULES_V09_2["duplicate_same_service"]["severity"],
                    package=anchor.package,
                    entry_id_primary=anchor.entry_id,
                    entry_id_secondary=other.entry_id,
                    title_primary=anchor.display_title,
                    title_secondary=other.display_title,
                    message=MESSAGES_V09_2["duplicate_same_service"].format(title=anchor.title),
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


def _is_verified_lep_rule(lep_rule: Dict[str, Any]) -> bool:
    return not str(lep_rule.get("lep_id", "")).startswith("LOCAL_")


def check_included_redundancy(entries: List[ParsedEntry], lep_rule_data: Dict[str, Any], counter: Dict[str, int]) -> List[RuleFinding]:
    findings: List[RuleFinding] = []
    if not RULES_V09_2["included_redundancy"]["enabled"]:
        return findings

    lep_lookup = build_lep_lookup(lep_rule_data)
    entries_by_package: Dict[str, List[ParsedEntry]] = defaultdict(list)
    for entry in entries:
        if entry.entry_type == "leistung" and entry.matched and entry.matched.lep_id:
            entries_by_package[entry.package].append(entry)

    seen_pairs = set()
    for package_entries in entries_by_package.values():
        by_lep_id = defaultdict(list)
        for entry in package_entries:
            by_lep_id[entry.matched.lep_id].append(entry)

        for entry in package_entries:
            lep_rule = lep_lookup.get(entry.matched.lep_id)
            if not lep_rule or not _is_verified_lep_rule(lep_rule):
                continue
            included_ids = [item.get("lep_id") for item in lep_rule.get("included", []) if item.get("lep_id")]
            for included_id in included_ids:
                for child in by_lep_id.get(included_id, []):
                    if child.entry_id == entry.entry_id:
                        continue
                    pair_key = tuple(sorted([entry.entry_id, child.entry_id])) + (entry.package,)
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)
                    findings.append(
                        RuleFinding(
                            finding_id=_next_finding_id(counter),
                            rule_type="included_redundancy",
                            severity=RULES_V09_2["included_redundancy"]["severity"],
                            package=entry.package,
                            entry_id_primary=entry.entry_id,
                            entry_id_secondary=child.entry_id,
                            title_primary=entry.display_title,
                            title_secondary=child.display_title,
                            message=MESSAGES_V09_2["included_redundancy"].format(child=child.title, parent=entry.title),
                            confidence=0.9,
                            payload={"parent_lep_id": entry.matched.lep_id, "child_lep_id": included_id},
                        )
                    )
    return findings


def check_excluded_but_separate_check(entries: List[ParsedEntry], lep_rule_data: Dict[str, Any], counter: Dict[str, int]) -> List[RuleFinding]:
    findings: List[RuleFinding] = []
    if not RULES_V09_2["excluded_but_separate_check"]["enabled"]:
        return findings

    lep_lookup = build_lep_lookup(lep_rule_data)
    entries_by_package: Dict[str, List[ParsedEntry]] = defaultdict(list)
    for entry in entries:
        if entry.entry_type == "leistung" and entry.matched and entry.matched.lep_id:
            entries_by_package[entry.package].append(entry)

    seen = set()
    for package_entries in entries_by_package.values():
        lep_ids_present = {entry.matched.lep_id for entry in package_entries if entry.matched and entry.matched.lep_id}
        for entry in package_entries:
            lep_rule = lep_lookup.get(entry.matched.lep_id)
            if not lep_rule or not _is_verified_lep_rule(lep_rule):
                continue
            for excluded in lep_rule.get("excluded", []):
                excluded_id = excluded.get("lep_id")
                excluded_title = excluded.get("title")
                if not excluded_id or excluded_id in lep_ids_present:
                    continue
                key = (entry.package, entry.entry_id, excluded_id)
                if key in seen:
                    continue
                seen.add(key)
                findings.append(
                    RuleFinding(
                        finding_id=_next_finding_id(counter),
                        rule_type="excluded_but_separate_check",
                        severity=RULES_V09_2["excluded_but_separate_check"]["severity"],
                        package=entry.package,
                        entry_id_primary=entry.entry_id,
                        entry_id_secondary=None,
                        title_primary=entry.display_title,
                        title_secondary=None,
                        message=MESSAGES_V09_2["excluded_but_separate_check"].format(excluded=excluded_title, parent=entry.title),
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
        "match_rate": round((len(matched) / len(services)) * 100, 2) if services else 0.0,
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


def run_engine_v09_2(parser_entries: List[Dict[str, Any]], lep_rules_path: str | Path, lep_aliases_path: str | Path) -> Dict[str, Any]:
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
