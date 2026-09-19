import unittest
import asyncio
import os
import tempfile
from types import SimpleNamespace

from application.controlled_test_envelope import ControlledTestEnvelope
from manual_mode import ManualChargeRequest, ManualSessionManager, ManualSessionState
from runtime.charge.profiles.manual import ManualChargeProfile


class Workstream113Tests(unittest.TestCase):
    def test_control_limit_is_run_local(self):
        envelope = ControlledTestEnvelope()
        envelope.validate(battery_voltage_v=13.0, voltage_v=14.1, current_a=0.9)
        with self.assertRaises(ValueError):
            envelope.validate(battery_voltage_v=13.0, voltage_v=14.1, current_a=0.91)

    def test_voltage_below_battery_is_rejected(self):
        with self.assertRaises(ValueError):
            ControlledTestEnvelope().validate(
                battery_voltage_v=13.2, voltage_v=13.1, current_a=0.5
            )

    def test_main_to_mix_uses_live_transaction_and_no_off_on_success(self):
        class Hass:
            def __init__(self):
                self.live = {
                    "switch": "on", "battery_voltage": 13.0,
                    "set_voltage_readback_v2": 14.1,
                    "set_current_readback_v2": 5.0,
                    "_meta": {
                        "set_voltage_readback_v2": {"status": "ok", "age_s": 0.0},
                        "set_current_readback_v2": {"status": "ok", "age_s": 0.0},
                    },
                }
                self.off_calls = 0

            async def get_all_live(self):
                return dict(self.live)

            async def set_current(self, value):
                self.live["set_current_readback_v2"] = float(value)
                self.live["_meta"]["set_current_readback_v2"]["age_s"] = 0.0
                return True

            async def set_voltage(self, value):
                self.live["set_voltage_readback_v2"] = float(value)
                self.live["_meta"]["set_voltage_readback_v2"]["age_s"] = 0.0
                return True

            async def turn_off(self, entity_id=None):
                self.off_calls += 1
                self.live["switch"] = "off"
                return True

        with tempfile.TemporaryDirectory() as directory:
            hass = Hass()
            app = SimpleNamespace(hass=hass, charge_controller=SimpleNamespace(is_active=False))
            manager = ManualSessionManager(app, session_file=os.path.join(directory, "session.json"))
            profile = ManualChargeProfile.from_mapping({"main": {"voltage_v": 14.1, "current_a": 5.0, "minimum_current_a": 2.3, "hold_hours": 0.001}, "mix": {"voltage_v": 15.1, "current_a": 0.9, "delta_voltage_v": 0.001, "delta_current_a": 0.001, "hold_hours": 0.04}})
            manager.request = ManualChargeRequest(14.1, 5.0, profile=profile, stage="main")
            manager.state = ManualSessionState.ACTIVE
            manager.stop_reason = "manual_main_hold_complete"
            manager.identity_integration.create_for_start(profile="Baic72")
            manager._manual_start_event_emitted = True
            decision = manager.phase_lifecycle.evaluate_main(
                profile=profile, voltage_v=14.1, current_a=2.3, is_cv=True,
                now=100.0,
            )
            self.assertIsNone(decision)
            decision = manager.phase_lifecycle.evaluate_main(
                profile=profile, voltage_v=14.1, current_a=2.3, is_cv=True,
                now=104.0,
            )
            self.assertIsNotNone(decision)
            asyncio.run(manager._advance_profile_to_mix())
            self.assertEqual(manager.request.stage, "mix")
            self.assertEqual(manager.stop_reason, "")
            self.assertEqual(manager.phase_transition_reason, "manual_main_to_mix")
            self.assertEqual(hass.off_calls, 0)


if __name__ == "__main__":
    unittest.main()
