"""
PRISMA - Matcher v09
====================

Aufgabe dieses Moduls:
- lädt Alias- und LEP-Regeldaten
- ordnet PRISMA-Leistungen möglichst deterministisch einem LEP-Eintrag zu

Reihenfolge des Matchings:
1. Exakter Alias-Match
2. Normalisierter Alias-Match
3. Exakter Titel-Match gegen LEP-Regeln
4. Normalisierter Titel-Match gegen LEP-Regeln
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .models_v09 import MatchResult, ParsedEntry


def normalize_text(value: str) -> str:
    """Normalisiert Text für robuste Vergleiche."""
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = text.replace(" - ", "-")
    return text


def build_lookup_tables(alias_data: Dict[str, Any], lep_rule_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Baut Lookup-Tabellen für Alias- und Titel-Matches."""
    alias_exact: Dict[str, Dict[str, Any]] = {}
    alias_normalized: Dict[str, Dict[str, Any]] = {}
    lep_title_exact: Dict[str, Dict[str, Any]] = {}
    lep_title_normalized: Dict[str, Dict[str, Any]] = {}

    for entry in lep_rule_data.get("entries", []):
        title = entry.get("title", "")
        if title:
            lep_title_exact[title] = entry
            lep_title_normalized[normalize_text(title)] = entry

    for alias in alias_data.get("aliases", []):
        prisma_title = alias.get("prisma_title", "")
        if prisma_title:
            alias_exact[prisma_title] = alias
            alias_normalized[normalize_text(prisma_title)] = alias

    return {
        "alias_exact": alias_exact,
        "alias_normalized": alias_normalized,
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
    )


def match_single_entry(entry: ParsedEntry, lookup: Dict[str, Dict[str, Any]]) -> Optional[MatchResult]:
    """Ordnet eine Leistung einem LEP-Eintrag zu."""
    if entry.entry_type != "leistung":
        return None

    title = entry.title
    title_normalized = normalize_text(title)

    alias = lookup["alias_exact"].get(title)
    if alias:
        lep_entry = lookup["lep_title_exact"].get(alias.get("lep_title")) or lookup["lep_title_normalized"].get(normalize_text(alias.get("lep_title", "")))
        if lep_entry:
            return _match_from_lep_entry(lep_entry, "alias_exact", title, 1.0)

    alias = lookup["alias_normalized"].get(title_normalized)
    if alias:
        lep_entry = lookup["lep_title_exact"].get(alias.get("lep_title")) or lookup["lep_title_normalized"].get(normalize_text(alias.get("lep_title", "")))
        if lep_entry:
            return _match_from_lep_entry(lep_entry, "alias_normalized", title, 0.95)

    lep_entry = lookup["lep_title_exact"].get(title)
    if lep_entry:
        return _match_from_lep_entry(lep_entry, "lep_title_exact", title, 0.9)

    lep_entry = lookup["lep_title_normalized"].get(title_normalized)
    if lep_entry:
        return _match_from_lep_entry(lep_entry, "lep_title_normalized", title, 0.85)

    return None


def apply_matching(entries: List[ParsedEntry], alias_data: Dict[str, Any], lep_rule_data: Dict[str, Any]) -> List[ParsedEntry]:
    """Wendet das Matching auf alle ParsedEntry-Objekte an."""
    lookup = build_lookup_tables(alias_data, lep_rule_data)
    for entry in entries:
        entry.matched = match_single_entry(entry, lookup)
    return entries
