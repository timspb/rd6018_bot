import unittest

from rd_control_mode import RdControlMode
from rd_operation_mode import (
    RdOperatingState,
    RdOperationMode,
    RdOwnership,
    operating_state_from_control_mode,
)


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

    def test_existing_pb_managed_maps_to_bot_managed(self):
        state = operating_state_from_control_mode(RdControlMode.PB_MANAGED)

        self.assertEqual(state, RdOperatingState.bot_managed())
        self.assertTrue(state.control_plane_required)
        self.assertTrue(state.managed_edge_lease_required)

    def test_existing_hands_off_maps_to_external_autonomous(self):
        state = operating_state_from_control_mode(RdControlMode.HANDS_OFF)

        self.assertEqual(state, RdOperatingState.external_autonomous())
        self.assertFalse(state.control_plane_required)
        self.assertFalse(state.external_temperature_required_by_mode)

    def test_persisted_string_values_map_identically(self):
        self.assertEqual(
            operating_state_from_control_mode("pb_managed"),
            RdOperatingState.bot_managed(),
        )
        self.assertEqual(
            operating_state_from_control_mode("hands_off"),
            RdOperatingState.external_autonomous(),
        )

    def test_unknown_or_empty_legacy_mode_never_infers_autonomous(self):
        for raw in (None, "", "autonomous", "unknown", object()):
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(ValueError, "unsupported legacy RD control mode"):
                    operating_state_from_control_mode(raw)


if __name__ == "__main__":
    unittest.main()
