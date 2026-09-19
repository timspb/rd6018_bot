import inspect
import unittest

from application.controlled_test_envelope import ControlledTestEnvelope
from application.manual_execution_boundary import ManualExecutionBoundary
from application.manual_phase_lifecycle import ManualPhaseLifecycle


class Workstream114PostMigrationTests(unittest.TestCase):
    def test_manual_mode_has_no_direct_physical_setter_bypass(self):
        import manual_mode

        source = inspect.getsource(manual_mode)
        self.assertNotIn("self.app.hass.set_current", source)
        self.assertNotIn("self.app.hass.set_voltage", source)

    def test_main_mix_decision_is_v3_lifecycle_output(self):
        self.assertTrue(hasattr(ManualPhaseLifecycle, "evaluate_main"))
        self.assertTrue(hasattr(ManualExecutionBoundary, "apply"))

    def test_controlled_envelope_is_not_global_safety_policy(self):
        ControlledTestEnvelope().validate(
            battery_voltage_v=13.0, voltage_v=14.1, current_a=0.9
        )


if __name__ == "__main__":
    unittest.main()
