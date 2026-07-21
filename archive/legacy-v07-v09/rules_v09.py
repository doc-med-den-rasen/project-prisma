"""
PRISMA - Regeldefinitionen v09
==============================

Hier stehen die aktivierbaren Regeltypen und ihre Standardschwere.
Die eigentliche Prüflogik lebt in engine_v09.py.
"""

RULES_V09 = {
    "duplicate_same_service": {
        "enabled": True,
        "severity": "medium",
    },
    "included_redundancy": {
        "enabled": True,
        "severity": "medium",
    },
    "excluded_but_separate_check": {
        "enabled": True,
        "severity": "low",
    },
}

MESSAGES_V09 = {
    "duplicate_same_service": (
        "Leistung wirkt doppelt geplant: {title}. "
        "Titel, Zyklus und Detailkontext sehen sehr ähnlich aus."
    ),
    "included_redundancy": (
        "{child} ist in {parent} enthalten und wirkt daher wahrscheinlich redundant."
    ),
    "excluded_but_separate_check": (
        "{excluded} ist in {parent} nicht enthalten. "
        "Bitte prüfen, ob diese Leistung separat relevant ist."
    ),
}
