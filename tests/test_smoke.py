from pathlib import Path
import unittest

from engine.engine import run_engine
from parser import parse_pflegeplan_txt


PROJECT_DIR = Path(__file__).resolve().parents[1]
RULES_PATH = PROJECT_DIR / "data" / "lep_rules.json"
ALIASES_PATH = PROJECT_DIR / "data" / "lep_aliases.json"


def service(entry_id: str, title: str, package: str = "01 Bewegung") -> dict:
    return {
        "entry_id": entry_id,
        "parent_entry_id": None,
        "row_type": "leistung",
        "title": title,
        "display_title": title,
        "package": package,
        "package_raw": package,
        "zyklentext": "",
        "zyklus_info": {},
        "entry_origin": "manuell",
        "package_is_pmd": False,
        "title_row": 1,
        "status_row": 2,
        "instance_index": 1,
        "instance_total_same_title": 1,
    }


class ParserSmokeTests(unittest.TestCase):
    def test_grabber_txt_keeps_active_and_drops_discontinued_entries(self) -> None:
        raw_text = """Pflegeplan
Pfleg OE: 00000015,\tFachabt.: THG,\tStartdat: 01.01.2026,\tEndedat.: 02.01.2026
Bezeichnung Pflegeplaneintrag\tStatus\tEvaluierung\tZyklentext\tAnlegeDat.\tErf.zeit\tAngelegt von
01 Bewegung (PMD)
Aktiv\t\t\t01.01.2026\t08:00\tTEST
In das Bett mobilisieren
Aktiv\t\t3x tgl.\t01.01.2026\t08:00\tTEST
An Bettrand mobilisieren
Abgesetzt\t\t1x tgl.\t01.01.2026\t08:00\tTEST
"""

        entries, stats = parse_pflegeplan_txt(raw_text, source_name="smoke.txt")
        services = [entry["title"] for entry in entries if entry["row_type"] == "leistung"]

        self.assertEqual(services, ["In das Bett mobilisieren"])
        self.assertEqual(stats["logical_pairs_abgesetzt"], 1)
        self.assertEqual(stats["metadata"]["Fachabt."], "THG")


class EngineSmokeTests(unittest.TestCase):
    def test_verified_inclusion_rule_is_reported(self) -> None:
        entries = [
            service("E00001", "In das Bett mobilisieren"),
            service("E00002", "An Bettrand mobilisieren"),
        ]

        result = run_engine(entries, RULES_PATH, ALIASES_PATH)
        finding_types = [finding.rule_type for finding in result["findings"]]

        self.assertEqual(result["match_summary"]["verified_match_count"], 2)
        self.assertIn("included_redundancy", finding_types)

    def test_similar_title_is_not_matched_automatically(self) -> None:
        entries = [service("E00001", "Vitalzeichen mit Monitor messen", "Überwachungen")]

        result = run_engine(entries, RULES_PATH, ALIASES_PATH)

        self.assertEqual(result["match_summary"]["matched_count"], 0)
        self.assertEqual(result["match_summary"]["unmatched_count"], 1)


if __name__ == "__main__":
    unittest.main()
