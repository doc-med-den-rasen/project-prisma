import unittest

from targeted_check import (
    normalize_exact,
    parse_service_lines,
    run_targeted_check,
)


RULES = {
    "entries": [
        {
            "lep_id": "I_PARENT",
            "title": "Transfer durchführen",
            "included": [
                {"lep_id": "I_CHILD", "title": "In das Bett mobilisieren"}
            ],
            "excluded": [
                {"lep_id": "I_OTHER", "title": "Transfertraining durchführen"}
            ],
            "active": True,
        },
        {
            "lep_id": "I_CHILD",
            "title": "In das Bett mobilisieren",
            "included": [],
            "excluded": [],
            "active": True,
        },
        {
            "lep_id": "I_OTHER",
            "title": "Transfertraining durchführen",
            "included": [],
            "excluded": [
                {"lep_id": "I_PARENT", "title": "Transfer durchführen"}
            ],
            "active": True,
        },
        {
            "lep_id": "LOCAL_VITAL",
            "title": "Vitalzeichen messen",
            "included": [],
            "excluded": [],
            "active": True,
            "source_type": "local_provisional",
        },
    ]
}

ALIASES = {
    "aliases": [
        {
            "prisma_title": "Transfer",
            "lep_title": "Transfer durchführen",
            "lep_id": "I_PARENT",
            "synonyms": [],
            "package_scopes": [],
        },
        {
            "prisma_title": "Bettmobilisation",
            "lep_title": "In das Bett mobilisieren",
            "lep_id": "I_CHILD",
            "synonyms": [],
            "package_scopes": ["01 Bewegung"],
        },
    ]
}


class TargetedParserTests(unittest.TestCase):
    def test_cycle_and_status_are_separated(self) -> None:
        parsed = parse_service_lines(
            "In das Bett mobilisieren PV_3XTGL5 Aktiv\n"
            "Transfer durchführen P_EINMAL Aktiv"
        )

        self.assertEqual(parsed[0].title, "In das Bett mobilisieren")
        self.assertEqual(parsed[0].cycle, "PV_3XTGL5")
        self.assertEqual(parsed[0].status, "Aktiv")
        self.assertEqual(parsed[1].title, "Transfer durchführen")
        self.assertEqual(parsed[1].cycle, "P_EINMAL")

    def test_plain_titles_are_supported(self) -> None:
        parsed = parse_service_lines("Transfer durchführen")
        self.assertEqual(parsed[0].title, "Transfer durchführen")
        self.assertTrue(parsed[0].is_active)

    def test_inactive_lines_are_identified(self) -> None:
        parsed = parse_service_lines("Transfer durchführen P_EINMAL Abgesetzt")
        self.assertFalse(parsed[0].is_active)


class TargetedRuleTests(unittest.TestCase):
    def test_confirmed_inclusion_is_reported_for_selected_pair(self) -> None:
        result = run_targeted_check(
            "Transfer durchführen Aktiv\nIn das Bett mobilisieren Aktiv",
            RULES,
            ALIASES,
        )

        self.assertEqual(len(result.included), 1)
        self.assertEqual(result.included[0].related_id, "I_CHILD")

    def test_exclusion_is_only_reported_when_both_services_are_present(self) -> None:
        parent_only = run_targeted_check(
            "Transfer durchführen Aktiv",
            RULES,
            ALIASES,
        )
        selected_pair = run_targeted_check(
            "Transfer durchführen Aktiv\nTransfertraining durchführen Aktiv",
            RULES,
            ALIASES,
        )

        self.assertEqual(parent_only.excluded, [])
        self.assertEqual(len(selected_pair.excluded), 1)

    def test_similar_title_is_never_matched(self) -> None:
        result = run_targeted_check(
            "Vitalzeichen mit Monitor messen Aktiv",
            RULES,
            ALIASES,
        )

        self.assertEqual(len(result.matched), 0)
        self.assertEqual(len(result.unmatched), 1)

    def test_package_scoped_alias_is_not_used_without_package_context(self) -> None:
        result = run_targeted_check("Bettmobilisation Aktiv", RULES, ALIASES)
        self.assertEqual(len(result.unmatched), 1)

    def test_unscoped_confirmed_alias_is_allowed(self) -> None:
        result = run_targeted_check("Transfer Aktiv", RULES, ALIASES)
        self.assertEqual(result.matched[0].lep_id, "I_PARENT")

    def test_exact_normalization_does_not_merge_different_titles(self) -> None:
        self.assertEqual(
            normalize_exact("  TRANSFER   durchführen "),
            normalize_exact("Transfer durchführen"),
        )
        self.assertNotEqual(
            normalize_exact("Vitalzeichen messen"),
            normalize_exact("Vitalzeichen mit Monitor messen"),
        )


if __name__ == "__main__":
    unittest.main()

