"""Gezielter Copy-Paste-Leistungscheck für PRISMA.

Das Modul bewertet keinen vollständigen Pflegeplan. Es erkennt ausschließlich
eingefügte Leistungen per exaktem Titel beziehungsweise bestätigtem Alias und
prüft bestätigte Ein-/Ausschlussbeziehungen zwischen diesen Leistungen.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable


INACTIVE_STATUSES = {"abgesetzt", "storniert", "inaktiv"}
STATUS_PATTERN = r"(?:Aktiv|Abgesetzt|Storniert|Inaktiv)"
CYCLE_PATTERN = r"P(?:V)?_[A-ZÄÖÜ0-9_]+"


@dataclass(frozen=True)
class ServiceLine:
    line_number: int
    raw_line: str
    title: str
    cycle: str = ""
    status: str = ""

    @property
    def is_active(self) -> bool:
        return self.status.casefold() not in INACTIVE_STATUSES


@dataclass(frozen=True)
class ServiceMatch:
    service: ServiceLine
    lep_id: str | None
    lep_title: str | None
    match_type: str

    @property
    def is_matched(self) -> bool:
        return bool(self.lep_id)


@dataclass(frozen=True)
class RelationFinding:
    relation_type: str
    parent_id: str
    parent_title: str
    related_id: str
    related_title: str


@dataclass
class TargetedCheckResult:
    parsed: list[ServiceLine] = field(default_factory=list)
    inactive: list[ServiceLine] = field(default_factory=list)
    matches: list[ServiceMatch] = field(default_factory=list)
    included: list[RelationFinding] = field(default_factory=list)
    excluded: list[RelationFinding] = field(default_factory=list)
    duplicates: dict[str, list[ServiceMatch]] = field(default_factory=dict)
    without_relation: list[ServiceMatch] = field(default_factory=list)

    @property
    def active_count(self) -> int:
        return len(self.matches)

    @property
    def matched(self) -> list[ServiceMatch]:
        return [item for item in self.matches if item.is_matched]

    @property
    def unmatched(self) -> list[ServiceMatch]:
        return [item for item in self.matches if not item.is_matched]


def normalize_exact(value: str) -> str:
    """Minimale Normalisierung für exakte Vergleiche, niemals Fuzzy-Matching."""
    text = str(value or "").strip().casefold()
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"\s*\[\d+/\d+\]\s*$", "", text)
    return re.sub(r"\s+", " ", text)


def parse_service_lines(raw_text: str) -> list[ServiceLine]:
    """Zerlegt eine einfache Copy-Paste-Liste in Leistung, Zyklus und Status."""
    parsed: list[ServiceLine] = []

    line_pattern = re.compile(
        rf"^(?P<title>.+?)"
        rf"(?:\s+(?P<cycle>{CYCLE_PATTERN}))?"
        rf"(?:\s+(?P<status>{STATUS_PATTERN}))?$",
        flags=re.IGNORECASE,
    )

    for line_number, raw_line in enumerate(str(raw_text or "").splitlines(), start=1):
        compact = re.sub(r"\s+", " ", raw_line).strip()
        if not compact:
            continue

        match = line_pattern.fullmatch(compact)
        if not match:
            parsed.append(
                ServiceLine(
                    line_number=line_number,
                    raw_line=raw_line,
                    title=compact,
                )
            )
            continue

        parsed.append(
            ServiceLine(
                line_number=line_number,
                raw_line=raw_line,
                title=match.group("title").strip(),
                cycle=(match.group("cycle") or "").upper(),
                status=(match.group("status") or "").capitalize(),
            )
        )

    return parsed


def _unique_candidate(candidates: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    by_id = {
        str(candidate.get("lep_id")): candidate
        for candidate in candidates
        if candidate.get("lep_id")
    }
    if len(by_id) != 1:
        return None
    return next(iter(by_id.values()))


def _build_lookups(
    rule_data: dict[str, Any],
    alias_data: dict[str, Any],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    rules_by_title: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rules_by_id: dict[str, dict[str, Any]] = {}

    for entry in rule_data.get("entries", []):
        if not entry.get("active", True) or not entry.get("lep_id"):
            continue
        rules_by_id[str(entry["lep_id"])] = entry
        if entry.get("title"):
            rules_by_title[normalize_exact(entry["title"])].append(entry)

    aliases_by_title: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for alias in alias_data.get("aliases", []):
        # Ohne Paketkontext sind paketgebundene Aliase nicht eindeutig genug.
        if alias.get("package_scopes"):
            continue

        target = rules_by_id.get(str(alias.get("lep_id") or ""))
        if not target and alias.get("lep_title"):
            target = _unique_candidate(
                rules_by_title.get(normalize_exact(alias["lep_title"]), [])
            )
        if not target:
            continue

        values = [alias.get("prisma_title"), *(alias.get("synonyms") or [])]
        for value in values:
            if value:
                aliases_by_title[normalize_exact(value)].append(target)

    return rules_by_title, aliases_by_title


def match_services(
    services: Iterable[ServiceLine],
    rule_data: dict[str, Any],
    alias_data: dict[str, Any],
) -> list[ServiceMatch]:
    rules_by_title, aliases_by_title = _build_lookups(rule_data, alias_data)
    results: list[ServiceMatch] = []

    for service in services:
        normalized = normalize_exact(service.title)
        direct = _unique_candidate(rules_by_title.get(normalized, []))
        if direct:
            results.append(
                ServiceMatch(
                    service=service,
                    lep_id=str(direct["lep_id"]),
                    lep_title=str(direct.get("title") or service.title),
                    match_type="Exakter Titel",
                )
            )
            continue

        alias = _unique_candidate(aliases_by_title.get(normalized, []))
        if alias:
            results.append(
                ServiceMatch(
                    service=service,
                    lep_id=str(alias["lep_id"]),
                    lep_title=str(alias.get("title") or service.title),
                    match_type="Bestätigter Alias",
                )
            )
            continue

        results.append(
            ServiceMatch(
                service=service,
                lep_id=None,
                lep_title=None,
                match_type="Keine exakte Zuordnung",
            )
        )

    return results


def _is_confirmed_rule(entry: dict[str, Any]) -> bool:
    """Provisorische lokale Einträge dürfen keine fachliche Regel auslösen."""
    return entry.get("active", True) and entry.get("source_type") != "local_provisional"


def evaluate_relations(
    matches: Iterable[ServiceMatch],
    rule_data: dict[str, Any],
) -> tuple[list[RelationFinding], list[RelationFinding]]:
    matched = [item for item in matches if item.is_matched]
    selected_ids = {str(item.lep_id) for item in matched}
    rules_by_id = {
        str(entry.get("lep_id")): entry
        for entry in rule_data.get("entries", [])
        if entry.get("lep_id")
    }

    included: list[RelationFinding] = []
    excluded: list[RelationFinding] = []
    seen_included: set[tuple[str, str]] = set()
    seen_excluded_pairs: set[frozenset[str]] = set()

    # Die Reihenfolge der Eingabe bestimmt die nachvollziehbare Ausgabereihenfolge.
    for item in matched:
        parent_id = str(item.lep_id)
        rule = rules_by_id.get(parent_id)
        if not rule or not _is_confirmed_rule(rule):
            continue

        for relation in rule.get("included", []):
            related_id = str(relation.get("lep_id") or "")
            key = (parent_id, related_id)
            if not related_id or related_id not in selected_ids or key in seen_included:
                continue
            seen_included.add(key)
            included.append(
                RelationFinding(
                    relation_type="included",
                    parent_id=parent_id,
                    parent_title=str(rule.get("title") or item.lep_title),
                    related_id=related_id,
                    related_title=str(
                        relation.get("title")
                        or rules_by_id.get(related_id, {}).get("title")
                        or related_id
                    ),
                )
            )

        for relation in rule.get("excluded", []):
            related_id = str(relation.get("lep_id") or "")
            pair = frozenset((parent_id, related_id))
            if (
                not related_id
                or related_id not in selected_ids
                or pair in seen_excluded_pairs
            ):
                continue
            seen_excluded_pairs.add(pair)
            excluded.append(
                RelationFinding(
                    relation_type="excluded",
                    parent_id=parent_id,
                    parent_title=str(rule.get("title") or item.lep_title),
                    related_id=related_id,
                    related_title=str(
                        relation.get("title")
                        or rules_by_id.get(related_id, {}).get("title")
                        or related_id
                    ),
                )
            )

    return included, excluded


def run_targeted_check(
    raw_text: str,
    rule_data: dict[str, Any],
    alias_data: dict[str, Any],
) -> TargetedCheckResult:
    parsed = parse_service_lines(raw_text)
    inactive = [service for service in parsed if not service.is_active]
    active = [service for service in parsed if service.is_active]
    matches = match_services(active, rule_data, alias_data)
    included, excluded = evaluate_relations(matches, rule_data)

    by_id: dict[str, list[ServiceMatch]] = defaultdict(list)
    for item in matches:
        if item.lep_id:
            by_id[item.lep_id].append(item)
    duplicates = {
        lep_id: items for lep_id, items in by_id.items() if len(items) > 1
    }

    participating_ids = {
        finding.parent_id
        for finding in [*included, *excluded]
    } | {
        finding.related_id
        for finding in [*included, *excluded]
    }
    without_relation = [
        item
        for item in matches
        if item.is_matched and str(item.lep_id) not in participating_ids
    ]

    return TargetedCheckResult(
        parsed=parsed,
        inactive=inactive,
        matches=matches,
        included=included,
        excluded=excluded,
        duplicates=duplicates,
        without_relation=without_relation,
    )
