import copy
import unittest
from charge_controller_v2 import ChargeControllerV2
from pb_domain import BatteryCondition, ChargeIntent
from recovery_session import RecoveryTracePoint
from recovery_shadow import ShadowRecoveryRuntime
from signal_analyzer import SignalEvent


class DummyHass:
    pass


def _controller(mode):
    controller = ChargeControllerV2(DummyHass(), authoritative=True)
    controller.current_stage = controller.STAGE_MIX
    controller.is_cv = mode == "CV"
    controller.is_cc = mode == "CC"
    controller._v2_trace_session_id = f"session-{mode.lower()}"
    controller._v2_runtime = ShadowRecoveryRuntime(
        battery_id="test-battery",
        started_at=1000.0,
        intent=ChargeIntent.RECOVERY,
        condition_before=BatteryCondition.UNKNOWN,
    )
    return controller


def _observe(controller, mode, samples):
    runtime = controller._v2_runtime
    for timestamp, voltage, current in samples:
        point = RecoveryTracePoint(
            timestamp_s=timestamp,
            stage="Mix Mode",
            voltage_v=voltage,
            current_a=current,
            temp_c=27.0,
            is_cv=mode == "CV",
            is_cc=mode == "CC",
            target_voltage_v=16.5,
        )
        record = runtime.observe(point, output_is_on=True)
        controller._v2_session_signal_context = {
            "session_id": controller._v2_trace_session_id,
            "mode": mode,
            "output_on": True,
            "telemetry_valid": not record.analysis.has(SignalEvent.TELEMETRY_INVALID),
        }


class SignalAnalyzerDiagnosticSnapshotTests(unittest.TestCase):
    def test_cc_snapshot_exposes_vmax_and_reversal_state(self):
        controller = _controller("CC")
        _observe(controller, "CC", [(0, 16.40, 2.0), (120, 16.50, 2.0),
                                    (240, 16.46, 2.0), (290, 16.46, 2.0),
                                    (340, 16.46, 2.0)])
        snapshot = controller.signal_analyzer_diagnostic_snapshot()
        self.assertEqual(snapshot["mode"], "CC")
        self.assertAlmostEqual(snapshot["cc"]["voltage_max_v"], 16.50)
        self.assertEqual(snapshot["cc"]["delta_reference_v"], snapshot["cc"]["voltage_max_v"])
        self.assertGreaterEqual(snapshot["cc"]["voltage_reversal_confirmations"], 3)
        self.assertTrue(snapshot["cc"]["voltage_reversal_emitted"])

    def test_cv_snapshot_exposes_imin_and_reversal_state(self):
        controller = _controller("CV")
        _observe(controller, "CV", [(0, 16.40, 0.80), (120, 16.50, 0.66),
                                    (240, 16.50, 0.90), (290, 16.50, 0.90),
                                    (340, 16.50, 0.90)])
        snapshot = controller.signal_analyzer_diagnostic_snapshot()
        self.assertEqual(snapshot["mode"], "CV")
        self.assertAlmostEqual(snapshot["cv"]["current_min_a"], 0.66)
        self.assertEqual(snapshot["cv"]["delta_reference_a"], snapshot["cv"]["current_min_a"])
        self.assertGreaterEqual(snapshot["cv"]["current_reversal_confirmations"], 3)
        self.assertTrue(snapshot["cv"]["current_reversal_emitted"])

    def test_empty_snapshot_is_explicitly_unavailable(self):
        controller = _controller("CV")
        snapshot = controller.signal_analyzer_diagnostic_snapshot()
        self.assertFalse(snapshot["available"])
        self.assertFalse(snapshot["runtime_evidence_available"])
        self.assertIsNone(snapshot["last_sample"])

    def test_snapshot_is_read_only(self):
        controller = _controller("CV")
        _observe(controller, "CV", [(0, 16.40, 0.80), (120, 16.50, 0.66)])
        analyzer = controller._v2_runtime.tracker._analyzer
        before = copy.deepcopy(analyzer.__dict__)
        controller.signal_analyzer_diagnostic_snapshot()
        self.assertEqual(analyzer.__dict__, before)


if __name__ == "__main__":
    unittest.main()
