import unittest

from pb_domain import (
    BatteryChemistry,
    BatteryCondition,
    BatteryIdentity,
    BatteryLifecycle,
    ChargeContext,
    ChargeIntent,
)


class BatteryDomainTests(unittest.TestCase):
    def test_chemistry_is_independent_from_recovery_intent(self):
        identity = BatteryIdentity("agm-95", BatteryChemistry.AGM, 95)
        normal = ChargeContext(identity, ChargeIntent.NORMAL, BatteryCondition.HEALTHY)
        recovery = ChargeContext(
            identity,
            ChargeIntent.RECOVERY,
            BatteryCondition.REHYDRATED,
        )

        self.assertFalse(normal.is_recovery)
        self.assertTrue(recovery.is_recovery)
        self.assertEqual(normal.identity.chemistry, recovery.identity.chemistry)

    def test_refill_becomes_longitudinal_state(self):
        lifecycle = BatteryLifecycle()
        lifecycle.mark_refill(total_ml=240, per_cell_ml=40, timestamp=100.0)
        self.assertEqual(lifecycle.condition, BatteryCondition.REHYDRATED)
        self.assertEqual(lifecycle.water_added_total_ml, 240)
        self.assertEqual(lifecycle.cycles_since_refill, 0)

        lifecycle.record_completed_cycle()
        lifecycle.record_completed_cycle()
        self.assertEqual(lifecycle.cycles_since_refill, 2)


if __name__ == "__main__":
    unittest.main()
