"""
PRISMA - Matcher v10.1
======================

Konservativer Matcher für PRISMA:
- KEINE Fuzzy-/Ähnlichkeits-Autozuordnung
- KEINE Vorschläge auf Basis von "klingt ähnlich"
- Matches nur über exakte Alias-, Synonym- oder verifizierte LEP-Titel

Unbekannte Leistungen bleiben unbekannt und landen in der Review-/Sortierliste.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .models_v10_1 import MatchResult, ParsedEntry


def strip_instance_suffix(value: str) -> str:
    return re.sub(r"\s*\[\d+/\d+\]\s*$", "", str(value or "")).strip()


def normalize_text(value: str) -> str:
    """Normalisierung für exakte Vergleiche, nicht für Fuzzy-Matching."""
    text = strip_instance_suffix(str(value or "")).strip().lower()
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text)
    return text


def _package_scope_match(entry_package: str, package_scopes: List[str]) -> bool:
    if not package_scopes:
        return True
    entry_pkg_norm = normalize_text(entry_package)
    return any(normalize_text(scope) == entry_pkg_norm for scope in package_scopes)


def build_lookup_tables(alias_data: Dict[str, Any], lep_rule_data: Dict[str, Any]) -> Dict[str, Any]:
    lep_title_exact: Dict[str, Dict[str, Any]] = {}
    lep_title_normalized: Dict[str, Dict[str, Any]] = {}

    for entry in lep_rule_data.get("entries", []):
        title = entry.get("title", "")
        if title:
            lep_title_exact[title] = entry
            lep_title_normalized[normalize_text(title)] = entry

    return {
        "alias_data": alias_data,
        "lep_title_exact": lep_title_exact,
        "lep_title_normalized": lep_title_normalized,
    }


def _match_from_lep_entry(lep_entry: Dict[str, Any], match_type: str, source_value: str, confidence: float) -> MatchResult:
    return MatchResult(
        lep_id=lep_entry.get("lep_id"),
        lep_title=lep_entry.get("title"),
        structure_id=lep_entry.get("structure_id"),
        match_type=match_type,
        confidence=confidence,
        source_value=source_value,
        suggestions=[],
    )


def _iter_alias_candidates(entry: ParsedEntry, alias_data: Dict[str, Any]):
    entry_title_exact = strip_instance_suffix(entry.title)
    entry_title_norm = normalize_text(entry.title)
    entry_package = entry.package

    for alias in alias_data.get("aliases", []):
        if not _package_scope_match(entry_package, alias.get("package_scopes", []) or []):
            continue

        alias_titles = [alias.get("prisma_title", "")] + (alias.get("synonyms", []) or [])
        alias_titles = [strip_instance_suffix(a) for a in alias_titles if a]
        normalized_alias_titles = [normalize_text(a) for a in alias_titles if a]

        if entry_title_exact in alias_titles:
            yield alias, "alias_exact", 1.0
        elif entry_title_norm in normalized_alias_titles:
            yield alias, "alias_normalized", 0.97


def match_single_entry(entry: ParsedEntry, lookup: Dict[str, Any]) -> Optional[MatchResult]:
    if entry.entry_type != "leistung":
        return None

    title = strip_instance_suffix(entry.title)
    title_normalized = normalize_text(title)

    for alias, match_type, confidence in _iter_alias_candidates(entry, lookup["alias_data"]):
        lep_entry = (
            lookup["lep_title_exact"].get(alias.get("lep_title"))
            or lookup["lep_title_normalized"].get(normalize_text(alias.get("lep_title", "")))
        )
        if lep_entry:
            return _match_from_lep_entry(lep_entry, match_type, title, confidence)

    lep_entry = lookup["lep_title_exact"].get(title)
    if lep_entry:
        return _match_from_lep_entry(lep_entry, "lep_title_exact", title, 0.92)

    lep_entry = lookup["lep_title_normalized"].get(title_normalized)
    if lep_entry:
        return _match_from_lep_entry(lep_entry, "lep_title_normalized", title, 0.88)

    return MatchResult(
        lep_id=None,
        lep_title=None,
        structure_id=None,
        match_type="unmatched_needs_manual_review",
        confidence=0.0,
        source_value=title,
        suggestions=[],
    )


def apply_matching(entries: List[ParsedEntry], alias_data: Dict[str, Any], lep_rule_data: Dict[str, Any]) -> List[ParsedEntry]:
    lookup = build_lookup_tables(alias_data, lep_rule_data)
    for entry in entries:
        entry.matched = match_single_entry(entry, lookup)
    return entries
