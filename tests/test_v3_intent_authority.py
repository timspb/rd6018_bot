import pathlib
import unittest
from dataclasses import fields

from runtime.charge import ChargeIntent


class V3IntentAuthorityTests(unittest.TestCase):
    def test_charge_intent_schema_is_complete(self):
        self.assertEqual(
            {"target_voltage", "target_current", "next_stage", "completed", "reason"},
            {field.name for field in fields(ChargeIntent)},
        )

    def test_charge_intent_is_domain_data_only(self):
        intent = ChargeIntent(14.4, 2.0, "delta", False, "test")

        self.assertFalse(any(name in dir(intent) for name in ("turn_on", "turn_off", "set_voltage", "set_current")))
        with self.assertRaises(AttributeError):
            intent.reason = "mutated"

    def test_decision_ownership_inventory_covers_required_decisions(self):
        path = pathlib.Path(__file__).parents[1] / "docs" / "V3_PHASE7F_DECISION_OWNERSHIP.md"
        text = path.read_text(encoding="utf-8")
        for decision in (
            "target voltage",
            "target current",
            "stage",
            "completion",
            "program transitions",
            "enable/disable intent",
            "safety limits",
        ):
            self.assertIn(decision, text)


if __name__ == "__main__":
    unittest.main()
