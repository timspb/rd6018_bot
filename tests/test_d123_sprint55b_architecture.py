import unittest
from pathlib import Path

from charge_controller import ManagedChargeController
from mix_active_authority import MixActiveTimeAuthority


ROOT = Path(__file__).resolve().parents[1]


class Sprint55BArchitectureTests(unittest.TestCase):
    def test_production_uses_canonical_host_with_explicit_configuration(self):
        from production_controller import create_production_charge_host
        from pb_domain import BatteryCondition, ChargeIntent
        host = create_production_charge_host(None)
        self.assertIs(type(host), ManagedChargeController)
        self.assertTrue(host.host_configuration.production_extensions_enabled)
        self.assertEqual(host.host_configuration.restore_trace_default_intent, ChargeIntent.NORMAL)
        self.assertEqual(host.host_configuration.restore_trace_default_condition, BatteryCondition.UNKNOWN)
        self.assertIsNot(MixActiveTimeAuthority, ManagedChargeController)

    def test_diagnostic_and_mix_state_are_initialized_on_same_host(self):
        source = (ROOT / "charge_controller.py").read_text()
        self.assertIn("initialize_battery_fault_state(self)", source)
        self.assertIn("initialize_production_session_state(self)", source)
        self.assertIn("initialize_mix_active_authority(host)",
                      (ROOT / "application/production_session_extensions.py").read_text())
        self.assertNotIn("class MixActiveAuthorityMixin", (ROOT / "mix_active_authority.py").read_text())

    def test_guard_extension_mix_order_remains(self):
        controller = (ROOT / "charge_controller.py").read_text()
        guard = controller.index("read_guard(", controller.index("def try_restore_session"))
        extensions = controller.index("restore_production_session_state(", guard)
        extension = (ROOT / "application/production_session_extensions.py").read_text()
        ordinary = extension.index("restore_production_session_state")
        mix_load = extension.index("restore_mix_active_authority(host)", ordinary)
        self.assertLess(guard, extensions)
        self.assertLess(ordinary, mix_load)


if __name__ == "__main__":
    unittest.main()
