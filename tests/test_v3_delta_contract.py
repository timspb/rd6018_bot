import ast
import pathlib
import unittest

from runtime.charge import DELTA_TRANSITIONS, DeltaState, delta_cases


class V3DeltaContractTests(unittest.TestCase):
    def test_delta_vectors_load(self):
        self.assertEqual(4, len(delta_cases))
        self.assertEqual("delta-enter", delta_cases[0].case_id)
        self.assertEqual("delta-complete", delta_cases[2].case_id)
        for case in delta_cases:
            self.assertIsInstance(case.expected_intent.next_stage, str)

    def test_transition_table_is_consistent_with_vectors(self):
        transitions = {(source, condition, target, reason) for source, condition, target, reason in DELTA_TRANSITIONS}

        for case in delta_cases:
            self.assertIn(
                (case.current_state, case.condition, case.next_state, case.expected_intent.reason),
                transitions,
            )
        states = set(DeltaState)
        self.assertTrue(all(source in states and target in states for source, _, target, _ in DELTA_TRANSITIONS))

    def test_delta_contract_has_no_external_or_actuator_imports(self):
        path = pathlib.Path(__file__).parents[1] / "runtime" / "charge" / "contracts" / "delta.py"
        text = path.read_text(encoding="utf-8")
        forbidden = {"bot_legacy", "hass_api", "aiogram", "rd_control_mode", "safe_output", "turn_on", "turn_off"}
        self.assertTrue(forbidden.isdisjoint(text.split()))
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".")[0], forbidden)


if __name__ == "__main__":
    unittest.main()
