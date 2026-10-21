import unittest
from runtime.charge.link_session_recovery import RecoveryRoute, RecoveryAction, RecoveryAuthorizationInput, authorize_recovery_action

class ColdStartRecoveryTests(unittest.TestCase):
    def test_live_runtime_wires_cold_start_before_every_recovery_action(self):
        from pathlib import Path
        runtime=(Path(__file__).resolve().parents[1]/'runtime/production_runtime.py').read_text()
        start=runtime.index('cold_start = not getattr(charge_controller, "_d125_startup_observation_seen", False)')
        end=runtime.index('                # Resolve the current app-scoped port',start)
        self.assertIn('charge_controller._d125_startup_observation_seen = True',runtime[start:end])
        section=runtime[start:runtime.index('                charge_controller._was_unavailable = False',start)] if '                charge_controller._was_unavailable = False' in runtime[start:] else runtime[start:]
        self.assertEqual(section.count('cold_start=cold_start'),3)

    def test_persisted_idle_cold_start_never_enables(self):
        x=RecoveryAuthorizationInput(route=RecoveryRoute.IDLE_LINK,restored=True,auto_enable_authorized=True,safe_wait=False,ovp_triggered=False,ocp_triggered=False,input_voltage_ok=True,cold_start=True)
        self.assertEqual(authorize_recovery_action(x),RecoveryAction.SKIP)
    def test_active_link_cold_start_never_enables(self):
        x=RecoveryAuthorizationInput(route=RecoveryRoute.ACTIVE_LINK,restored=True,auto_enable_authorized=True,safe_wait=False,ovp_triggered=False,ocp_triggered=False,input_voltage_ok=True,cold_start=True)
        self.assertEqual(authorize_recovery_action(x),RecoveryAction.SKIP)
