
"""
PRISMA - Rules v10.1
====================
"""

RULES_V10_1 = {
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

MESSAGES_V10_1 = {
    "duplicate_same_service": "„{title}“ wirkt {count}x gleich geplant.",
    "included_redundancy_grouped": "Die Leistung „{parent}“ enthält wahrscheinlich bereits: {children}.",
    "excluded_but_separate_check_grouped": "Bei „{parent}“ sind folgende Leistungen nicht enthalten und separat zu prüfen: {excluded}.",
}
