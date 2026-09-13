import unittest

from runtime.diagnostics import DiagnosticAuthority
from runtime.ui.commands import (
    CommandContext, CommandStatus, ConfirmSafetyCommand, LegacyActionAdapter,
    SelectProfileCommand, StartChargeCommand, StopChargeCommand, UserCommandAdapter,
)


class V3UserCommandTests(unittest.TestCase):
    def _base(self, cls, **kwargs):
        return cls("id", 1.0, "test", "operator", **kwargs)

    def test_start_requires_confirmation_and_then_maps_to_domain_intent(self):
        adapter = UserCommandAdapter()
        command = self._base(StartChargeCommand, profile="agm")
        pending = adapter.adapt(command, CommandContext())
        accepted = adapter.adapt(self._base(StartChargeCommand, profile="agm", confirmed=True), CommandContext())
        self.assertEqual(pending.status, CommandStatus.REQUIRES_CONFIRMATION)
        self.assertEqual(accepted.intent.kind, "start_charge")

    def test_stop_and_profile_mapping(self):
        adapter = UserCommandAdapter()
        stop = adapter.adapt(self._base(StopChargeCommand, reason="operator request", confirmed=True), CommandContext())
        profile = adapter.adapt(self._base(SelectProfileCommand, profile="efb"), CommandContext())
        self.assertEqual(stop.intent.kind, "stop_charge")
        self.assertEqual(profile.intent.kind, "select_profile")

    def test_hard_stop_blocks_all_commands(self):
        command = self._base(SelectProfileCommand, profile="agm")
        result = UserCommandAdapter().adapt(command, CommandContext(authority=DiagnosticAuthority.HARD_STOP))
        self.assertEqual(result.status, CommandStatus.BLOCKED_BY_SAFETY)

    def test_legacy_action_mapping_has_one_owner(self):
        self.assertEqual(LegacyActionAdapter.map_action("START"), "start_charge")
        self.assertEqual(LegacyActionAdapter.map_action("STOP"), "stop_charge")
        with self.assertRaises(ValueError):
            LegacyActionAdapter.map_action("OUTPUT_ON")


if __name__ == "__main__":
    unittest.main()
