import unittest

from rd_operation_mode import RdOperatingState, RdOperationMode, RdOwnership


class RdOperationModeTests(unittest.TestCase):
    def test_bot_managed_requires_control_plane_and_edge_lease(self):
        state = RdOperatingState.bot_managed()

        state.validate_supported()
        self.assertTrue(state.bot_actuation_allowed)
        self.assertTrue(state.pb_application_allowed)
        self.assertTrue(state.control_plane_required)
        self.assertTrue(state.managed_edge_lease_required)
        self.assertTrue(state.external_temperature_required_by_mode)
        self.assertTrue(state.local_hardware_safety_required)

    def test_external_autonomous_is_generic_psu_not_pb(self):
        state = RdOperatingState.external_autonomous()

        state.validate_supported()
        self.assertFalse(state.bot_actuation_allowed)
        self.assertFalse(state.pb_application_allowed)
        self.assertFalse(state.control_plane_required)
        self.assertFalse(state.managed_edge_lease_required)
        self.assertFalse(state.external_temperature_required_by_mode)
        self.assertTrue(state.local_hardware_safety_required)

    def test_autonomous_does_not_assume_a_battery_load(self):
        state = RdOperatingState(RdOwnership.EXTERNAL, RdOperationMode.AUTONOMOUS)

        self.assertFalse(state.external_temperature_required_by_mode)
        self.assertFalse(state.pb_application_allowed)

    def test_unimplemented_cross_product_states_fail_closed(self):
        for state in (
            RdOperatingState(RdOwnership.BOT, RdOperationMode.AUTONOMOUS),
            RdOperatingState(RdOwnership.EXTERNAL, RdOperationMode.MANAGED),
        ):
            with self.subTest(state=state):
                with self.assertRaisesRegex(ValueError, "unsupported RD operating state"):
                    state.validate_supported()


if __name__ == "__main__":
    unittest.main()
