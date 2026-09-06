import json
import unittest
from pathlib import Path

CORPUS = json.loads((Path(__file__).parent / "corpus.json").read_text(encoding="utf-8"))


class CorpusContractTests(unittest.TestCase):
    def test_has_exactly_40_unique_realistic_messages(self) -> None:
        self.assertEqual(40, len(CORPUS))
        self.assertEqual(40, len({case["id"] for case in CORPUS}))
        self.assertTrue(all(case["text"].strip() for case in CORPUS))

    def test_all_required_scenario_families_are_covered(self) -> None:
        scenarios = {case["scenario"] for case in CORPUS}
        required = {
            "simple_task", "dated_task", "multiple", "waiting", "note",
            "reminder", "complete", "reschedule",
        }
        self.assertTrue(required <= scenarios)

    def test_missing_deadlines_stay_missing(self) -> None:
        no_deadline = [1, 2, 3, 7, 9, 13, 14, 15, 25, 26, 36, 38, 39, 40]
        by_id = {case["id"]: case for case in CORPUS}
        for case_id in no_deadline:
            with self.subTest(case_id=case_id):
                self.assertTrue(all(value is None for value in by_id[case_id]["due"]))

    def test_clarification_never_contains_operations(self) -> None:
        for case in CORPUS:
            if case.get("clarify"):
                with self.subTest(case_id=case["id"]):
                    self.assertEqual(0, case["count"])
                    self.assertEqual([], case["kinds"])

    def test_expected_shapes_are_consistent(self) -> None:
        for case in CORPUS:
            with self.subTest(case_id=case["id"]):
                self.assertEqual(case["count"], len(case["kinds"]))
                creates = case["kinds"].count("create")
                self.assertEqual(creates, len(case["types"]))
                allowed = {"create", "complete", "reschedule", "cancel"}
                self.assertTrue(set(case["kinds"]) <= allowed)
                if case.get("target_ids"):
                    mutations = sum(kind != "create" for kind in case["kinds"])
                    self.assertEqual(mutations, len(case["target_ids"]))


if __name__ == "__main__":
    unittest.main()
