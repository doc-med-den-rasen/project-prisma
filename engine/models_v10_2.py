
"""
PRISMA - Models v10.2
=====================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MatchSuggestion:
    lep_id: Optional[str]
    lep_title: str
    source_value: str
    score: float
    suggestion_type: str


@dataclass
class MatchResult:
    lep_id: Optional[str]
    lep_title: Optional[str]
    structure_id: Optional[str]
    match_type: str
    confidence: float
    source_value: str
    suggestions: List[MatchSuggestion] = field(default_factory=list)


@dataclass
class ParsedEntry:
    entry_id: str
    parent_entry_id: Optional[str]
    package: str
    package_raw: str
    entry_type: str
    title: str
    display_title: str
    details: List[str] = field(default_factory=list)
    zyklentext: str = ""
    zyklus_info: Dict[str, Any] = field(default_factory=dict)
    origin: str = "manuell"
    package_is_pmd: bool = False
    title_row: Optional[int] = None
    status_row: Optional[int] = None
    instance_index: int = 1
    instance_total_same_title: int = 1
    matched: Optional[MatchResult] = None


@dataclass
class RuleFinding:
    finding_id: str
    rule_type: str
    severity: str
    package: str
    entry_id_primary: str
    entry_id_secondary: Optional[str]
    title_primary: str
    title_secondary: Optional[str]
    message: str
    recommendation: str = ""
    confidence: float = 1.0
    payload: Dict[str, Any] = field(default_factory=dict)
