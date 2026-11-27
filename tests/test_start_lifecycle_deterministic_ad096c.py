import unittest
from unittest.mock import patch

from charge_controller import ManagedChargeController
from pb_domain import BatteryCondition, ChargeIntent
from runtime.charge.session import TraceIdentitySnapshot


class StartLifecycleDeterminismTests(unittest.TestCase):
    def _controller(self):
        controller = ManagedChargeController(object())
        controller._clear_session_file = lambda: setattr(controller, "cleared", True)
        controller.cleared = False
        return controller

    def test_default_start_keeps_wall_clock_and_clears_session(self):
        controller = self._controller()
        with patch("runtime.charge.lifecycle.time.time", return_value=1700000000.25), \
             patch("charge_controller.time.time", return_value=1700000000.25), \
             patch("runtime.charge.lifecycle.log_session_header"):
            controller.start("EFB", 70)
        self.assertEqual(controller.stage_start_time, 1700000000.25)
        self.assertEqual(controller.total_start_time, 1700000000.25)
        self.assertTrue(controller.cleared)
        self.assertEqual(controller._v2_trace_started_at, 1700000000.25)
        self.assertIsNotNone(controller._v2_trace_session_id)

    def test_pre_enable_abort_stop_does_not_clear_canonical_session_or_call_hardware(self):
        class NoPhysicalCalls:
            def __getattr__(self, name):
                if name.startswith(("turn_", "set_", "safe_")):
                    raise AssertionError(f"physical API called: {name}")
                raise AttributeError(name)

        controller = ManagedChargeController(NoPhysicalCalls())
        cleared = []
        controller._clear_session_file = lambda: cleared.append(True)
        with patch("runtime.charge.lifecycle.log_session_header"):
            controller.start("EFB", 70, now_s=1700000000.0, clear_session=False)
        controller.stop(clear_session=False)
        self.assertEqual(controller.current_stage, controller.STAGE_IDLE)
        self.assertEqual(cleared, [])

    def test_supplied_start_clock_and_trace_are_exact_and_do_not_clear(self):
        controller = self._controller()
        identity = TraceIdentitySnapshot(
            session_id="candidate-session", started_at=1700000123.5,
            battery_id="bank-a", intent="normal", condition_before="healthy",
        )
        controller.configure_recovery_context(
            battery_id="bank-a", intent=ChargeIntent.NORMAL,
            condition_before=BatteryCondition.HEALTHY,
        )
        with patch("runtime.charge.lifecycle.time.time", side_effect=AssertionError("clock read")), \
             patch("charge_controller.time.time", side_effect=AssertionError("clock read")), \
             patch('runtime.charge.session.time.time', side_effect=AssertionError("clock read")), \
             patch("runtime.charge.lifecycle.log_session_header"), \
             patch("runtime.charge.lifecycle.logger.info"):
            controller.start(
                "EFB", 70, now_s=identity.started_at,
                clear_session=False, trace_identity=identity,
            )
        self.assertEqual(controller.stage_start_time, identity.started_at)
        self.assertEqual(controller.total_start_time, identity.started_at)
        self.assertEqual(controller._v2_trace_started_at, identity.started_at)
        self.assertEqual(controller._v2_trace_session_id, identity.session_id)
        self.assertEqual(controller._v2_battery_id, identity.battery_id)
        self.assertFalse(controller.cleared)


if __name__ == "__main__":
    unittest.main()
