import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from diagnostic_controller import DiagnosticProductionChargeControllerV2
from mix_active_authority import MixActiveTimeAuthority
from recovery_policy import RecoveryDecision


class DummyHass:
    pass


class Clock:
    def __init__(self, value):
        self.value = float(value)

    def __call__(self):
        return self.value


class MixActiveTimeoutIntegrationTests(unittest.TestCase):
    def test_production_controller_uses_durable_active_budget_for_mix_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            mono = Clock(100.0)
            wall = Clock(1000.0)
            controller = DiagnosticProductionChargeControllerV2(
                DummyHass(),
                authoritative=True,
            )
            controller.current_stage = controller.STAGE_MIX
            controller.battery_type = controller.PROFILE_CA
            controller.ah_capacity = 72
            controller.stage_start_time = 499999.0  # wall-stage age is intentionally tiny
            controller.total_start_time = 1.0
            controller._v2_target_voltage_v = 16.5
            controller._v2_trace_session_id = "mix-session"
            controller._v2_trace_started_at = 1.0

            authority = MixActiveTimeAuthority(
                Path(tmp) / "mix-authority.json",
                monotonic=mono,
                wall_time=wall,
            )
            authority.begin("mix-session", active=True)
            mono.value += 20 * 3600
            wall.value += 20 * 3600
            authority.observe("mix-session", active=False)
            controller._mix_active_authority = authority

            metrics = SimpleNamespace(
                current_min_a=0.5,
                voltage_max_v=None,
            )
            record = SimpleNamespace(
                analysis=SimpleNamespace(metrics=metrics),
                decision=SimpleNamespace(decision=RecoveryDecision.CONTINUE),
            )
            actions = {}

            with patch("charge_logic.SESSION_FILE", str(Path(tmp) / "session.json")):
                decision = controller._apply_authoritative_decision(
                    record=record,
                    first_stage=None,
                    stage_before=controller.STAGE_MIX,
                    timestamp_s=500000.0,
                    voltage=16.4,
                    current=0.6,
                    temp=25.0,
                    ah=30.0,
                    is_cv=True,
                    is_cc=False,
                    actions=actions,
                )

            self.assertIsNotNone(decision)
            self.assertEqual(decision.reason, "MIX_TIMEOUT")
            self.assertEqual(decision.action.value, "stop_and_diagnose")
            self.assertEqual(controller.current_stage, controller.STAGE_DONE)
            self.assertTrue(actions.get("turn_off"))
            self.assertNotEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)
            self.assertEqual(authority.snapshot.terminal_reason, "MIX_TIMEOUT")
            self.assertAlmostEqual(authority.snapshot.elapsed_s, 20 * 3600)


if __name__ == "__main__":
    unittest.main()
