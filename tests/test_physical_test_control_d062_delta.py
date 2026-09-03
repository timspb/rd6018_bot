import asyncio
import types
import unittest

from physical_test_control_d062_delta import (
    PhysicalTestControlD062Delta,
    install_physical_test_control_d062_delta,
)
from rd_managed_adoption import ManagedAdoptionFingerprint
from signal_analyzer import SignalEvent


class FakeControl:
    def __init__(self):
        self._operation_lock = asyncio.Lock()
        self.dispatch_calls = 0
        self.dispatch = self.base_dispatch

    async def base_dispatch(self, request):
        self.dispatch_calls += 1
        return {"ok": True, "operation": "base"}

    @staticmethod
    def _require_fields(request, fields):
        if set(request) != fields:
            raise ValueError("unexpected or missing request fields")

    @staticmethod
    def _error(message):
        return {"ok": False, "error": str(message)}


class PhysicalTestControlD062DeltaTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def coordinator():
        return types.SimpleNamespace(
            current_authority=ManagedAdoptionFingerprint(15.10, 0.18, 15.30, 0.40),
            last_source_timestamp_s=2_000_000_000.0,
            started_at_s=2_000_000_000.0,
        )

    def test_synthetic_cv_delta_is_mode_correct_end_of_charge_evidence(self):
        analysis, details = PhysicalTestControlD062Delta._synthetic_delta_analysis(
            self.coordinator(),
            {
                "battery_voltage": 15.09,
                "current": 0.12,
                "temp_ext_v2": 27.0,
                "regulation_code": 0,
            },
        )
        self.assertIn(SignalEvent.END_OF_CHARGE_LIKELY, analysis.events)
        self.assertEqual(details["mode"], "CV")
        self.assertGreater(details["delta_current_a"], 0.03)
        self.assertLessEqual(details["reversal_current_a"], 0.18)
        self.assertTrue(details["synthetic_only"])

    def test_synthetic_cc_delta_is_mode_correct_end_of_charge_evidence(self):
        analysis, details = PhysicalTestControlD062Delta._synthetic_delta_analysis(
            self.coordinator(),
            {
                "battery_voltage": 12.90,
                "current": 0.17,
                "temp_ext_v2": 27.0,
                "regulation_code": 1,
            },
        )
        self.assertIn(SignalEvent.END_OF_CHARGE_LIKELY, analysis.events)
        self.assertEqual(details["mode"], "CC")
        self.assertAlmostEqual(details["delta_voltage_v"], 0.05)
        self.assertLessEqual(details["current_a"], 0.18)
        self.assertTrue(details["synthetic_only"])

    def test_synthetic_delta_rejects_unknown_regulation(self):
        with self.assertRaisesRegex(Exception, "authoritative CV/CC"):
            PhysicalTestControlD062Delta._synthetic_delta_analysis(
                self.coordinator(),
                {
                    "battery_voltage": 12.90,
                    "current": 0.17,
                    "temp_ext_v2": 27.0,
                    "regulation_code": 9,
                },
            )

    async def test_install_reuses_existing_socket_and_delegates_other_operations(self):
        app = types.SimpleNamespace()
        control = FakeControl()
        extension = install_physical_test_control_d062_delta(app, control)
        self.assertIsInstance(extension, PhysicalTestControlD062Delta)
        self.assertIs(install_physical_test_control_d062_delta(app, control), extension)
        result = await control.dispatch({"op": "status"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["operation"], "base")
        self.assertEqual(control.dispatch_calls, 1)

    async def test_delta_operation_rejects_extra_fields_before_execution(self):
        app = types.SimpleNamespace()
        control = FakeControl()
        extension = install_physical_test_control_d062_delta(app, control)

        async def must_not_run():
            self.fail("delta_hold_complete must not run when request fields widen")

        extension.delta_hold_complete = must_not_run
        result = await control.dispatch(
            {"op": "d062_test_delta_hold_complete", "extra": 1}
        )
        self.assertFalse(result["ok"])
        self.assertIn("unexpected or missing", result["error"])


if __name__ == "__main__":
    unittest.main()
