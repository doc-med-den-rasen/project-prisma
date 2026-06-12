"""
PRISMA - Rules v09.2
====================
"""

RULES_V09_2 = {
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

MESSAGES_V09_2 = {
    "duplicate_same_service": "„{title}“ wirkt mehrfach gleich geplant.",
    "included_redundancy": "„{child}“ ist in „{parent}“ enthalten und wirkt daher wahrscheinlich redundant.",
    "excluded_but_separate_check": "„{excluded}“ ist in „{parent}“ nicht enthalten. Bitte separat prüfen, ob es zusätzlich geplant werden sollte.",
}
