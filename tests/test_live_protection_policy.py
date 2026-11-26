"""Live software protection trip policy contracts."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

from runtime.safety.live_protection import evaluate_live_protection


def live(**overrides):
    data = {"protection_code": 0}
    data.update(overrides)
    return data


class LiveProtectionPolicyTests(unittest.TestCase):
    def test_precritical_internal_temperature_trips_with_output_or_charge(self):
        for state in ((True, False), (False, True)):
            result = evaluate_live_protection(
                live=live(),
                charge_active=state[0], output_on=state[1],
                internal_temperature_c=60.0, precritical_temperature_c=60.0,
            )
            self.assertEqual(result.triggers, ("TEMP_INT_PRECRITICAL",))
            self.assertTrue(result.shutdown_required)

    def test_temperature_below_threshold_and_inactive_output_is_clear(self):
        result = evaluate_live_protection(
            live=live(),
            charge_active=False, output_on=False,
            internal_temperature_c=59.9, precritical_temperature_c=60.0,
        )
        self.assertEqual(result.triggers, ())
        self.assertFalse(result.shutdown_required)

    def test_missing_temperature_does_not_invent_a_trip(self):
        result = evaluate_live_protection(
            live=live(),
            charge_active=True, output_on=True,
            internal_temperature_c=None, precritical_temperature_c=60.0,
        )
        self.assertEqual(result.triggers, ())
        self.assertEqual(result.evidence, ())

    def test_raw_protection_decoding_stays_inside_safety(self):
        source = Path("runtime/safety/live_protection.py").read_text(encoding="utf-8")
        self.assertIn("resolve_protection(live)", source)
        module = ast.parse(source)
        params = {
            arg.arg
            for node in ast.walk(module)
            if isinstance(node, ast.FunctionDef)
            for arg in node.args.kwonlyargs
        }
        self.assertIn("live", params)
        self.assertNotIn("ovp_triggered", params)
        self.assertNotIn("ocp_triggered", params)

    def test_production_runtime_dispatches_safety_decision_not_raw_bits(self):
        source = Path("runtime/production_runtime.py").read_text(encoding="utf-8")
        self.assertNotIn('_canonical_bool(live, "ovp_triggered")', source)
        self.assertNotIn('_canonical_bool(live, "ocp_triggered")', source)
        self.assertIn("live=live", source)
        self.assertNotIn('"OVP_TRIGGERED" in protection_decision.triggers', source)
        self.assertNotIn('"OCP_TRIGGERED" in protection_decision.triggers', source)
        self.assertIn('"OPP_TRIGGERED" in protection_decision.triggers', source)
        self.assertIn("await _hard_stop_charge()", source)

    def test_inactive_managed_charge_does_not_generate_hardware_trip_dispatch(self):
        for code in (1, 2, 3):
            with self.subTest(code=code):
                result = evaluate_live_protection(
                    live=live(protection_code=code),
                    charge_active=False, output_on=True,
                    internal_temperature_c=40.0, precritical_temperature_c=60.0,
                )
                self.assertEqual(result.triggers, ())

    def test_ovp_ocp_are_observed_but_not_software_trips_while_opp_is(self):
        for code in (1, 2, 3):
            with self.subTest(code=code):
                result = evaluate_live_protection(
                    live=live(protection_code=code),
                    charge_active=True, output_on=True,
                    internal_temperature_c=40.0, precritical_temperature_c=60.0,
                )
                self.assertEqual(result.triggers, ("OPP_TRIGGERED",) if code == 3 else ())
                self.assertEqual(result.shutdown_required, code == 3)


if __name__ == "__main__":
    unittest.main()
