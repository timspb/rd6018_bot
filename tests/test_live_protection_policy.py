"""D079: live protection belongs to a pure safety-policy module."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

from runtime.safety.live_protection import evaluate_live_protection


class LiveProtectionPolicyTests(unittest.TestCase):
    def evaluate(self, **overrides):
        values = dict(
            charge_active=True, output_on=True,
            ovp_triggered=False, ocp_triggered=False,
            internal_temperature_c=40.0, precritical_temperature_c=60.0,
        )
        values.update(overrides)
        return evaluate_live_protection(**values)

    def test_ovp_ocp_and_combination_keep_priority(self):
        self.assertEqual(self.evaluate(ovp_triggered=True).triggers, ("OVP_TRIGGERED",))
        self.assertEqual(self.evaluate(ocp_triggered=True).triggers, ("OCP_TRIGGERED",))
        self.assertEqual(
            self.evaluate(ovp_triggered=True, ocp_triggered=True).triggers,
            ("OVP_TRIGGERED", "OCP_TRIGGERED"),
        )

    def test_psu_temperature_at_threshold_and_with_output_only(self):
        self.assertEqual(
            self.evaluate(internal_temperature_c=60).triggers,
            ("TEMP_INT_PRECRITICAL",),
        )
        self.assertEqual(
            self.evaluate(charge_active=False, output_on=True,
                          internal_temperature_c=61).triggers,
            ("TEMP_INT_PRECRITICAL",),
        )
        self.assertFalse(
            self.evaluate(charge_active=False, output_on=False,
                          internal_temperature_c=80).shutdown_required
        )

    def test_inactive_charge_ignores_ovp_and_ocp_flags(self):
        self.assertEqual(
            self.evaluate(charge_active=False, output_on=False,
                          ovp_triggered=True, ocp_triggered=True).triggers, ()
        )

    def test_unknown_evidence_does_not_invent_fault(self):
        result = self.evaluate(
            ovp_triggered=None, ocp_triggered=None, internal_temperature_c=None)
        self.assertEqual(result.triggers, ())
        self.assertEqual(result.evidence, ())

    def test_both_electrical_and_thermal_order(self):
        result = self.evaluate(ovp_triggered=True, ocp_triggered=True,
                               internal_temperature_c=62)
        self.assertEqual(
            result.triggers,
            ("OVP_TRIGGERED", "OCP_TRIGGERED", "TEMP_INT_PRECRITICAL"),
        )

    def test_production_runtime_delegates_without_second_policy_branch(self):
        source = Path("runtime/production_runtime.py").read_text(encoding="utf-8")
        self.assertIn("protection_decision = evaluate_live_protection(", source)
        for trigger in ("OVP_TRIGGERED", "OCP_TRIGGERED", "TEMP_INT_PRECRITICAL"):
            self.assertIn(f'if "{trigger}" in protection_decision.triggers:', source)
        self.assertNotIn(
            "if charge_controller.is_active and (ovp_triggered or ocp_triggered):",
            source,
        )
        module = ast.parse(Path("runtime/safety/live_protection.py")
                           .read_text(encoding="utf-8"))
        names = [
            node.module or ""
            for node in ast.walk(module)
            if isinstance(node, ast.ImportFrom)
        ]
        self.assertFalse(any(
            name.startswith(("application", "runtime.physical", "runtime.output"))
            for name in names
        ))


if __name__ == "__main__":
    unittest.main()
