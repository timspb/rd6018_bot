import unittest

from pb_domain import (
    BatteryChemistry,
    BatteryCondition,
    BatteryIdentity,
    ChargeContext,
    ChargeIntent,
)
from recipe_engine import select_recipe_envelope


def context(chemistry, intent, condition=BatteryCondition.HEALTHY, capacity=70):
    return ChargeContext(
        BatteryIdentity("b1", chemistry, capacity),
        intent,
        condition,
    )


class RecipeEngineTests(unittest.TestCase):
    def test_agm_normal_and_recovery_are_distinct(self):
        normal = select_recipe_envelope(
            context(BatteryChemistry.AGM, ChargeIntent.NORMAL)
        )
        recovery = select_recipe_envelope(
            context(BatteryChemistry.AGM, ChargeIntent.RECOVERY)
        )
        self.assertEqual(normal.voltage_ceiling_v, 15.0)
        self.assertEqual(recovery.voltage_ceiling_v, 16.3)
        self.assertFalse(normal.allows_voltage(16.3))
        self.assertTrue(recovery.allows_voltage(16.3))

    def test_efb_17_5_requires_explicit_expert_conditioning(self):
        ordinary = select_recipe_envelope(
            context(BatteryChemistry.EFB, ChargeIntent.CONDITIONING),
            expert_high_voltage=False,
        )
        expert = select_recipe_envelope(
            context(BatteryChemistry.EFB, ChargeIntent.CONDITIONING),
            expert_high_voltage=True,
        )
        self.assertEqual(ordinary.voltage_ceiling_v, 16.5)
        self.assertEqual(expert.voltage_ceiling_v, 17.5)
        self.assertFalse(ordinary.allows_voltage(17.5))
        self.assertTrue(expert.allows_voltage(17.5))

    def test_current_limits_are_capacity_relative_and_hardware_capped(self):
        efb = select_recipe_envelope(
            context(BatteryChemistry.EFB, ChargeIntent.CONDITIONING, capacity=100),
            expert_high_voltage=True,
        )
        self.assertAlmostEqual(efb.main_current_limit_a, 10.0)
        self.assertAlmostEqual(efb.hv_current_limit_a, 5.0)

        huge = select_recipe_envelope(
            context(BatteryChemistry.EFB, ChargeIntent.CONDITIONING, capacity=300),
            expert_high_voltage=True,
        )
        self.assertEqual(huge.main_current_limit_a, 12.0)
        self.assertEqual(huge.hv_current_limit_a, 12.0)

    def test_rehydrated_state_is_preserved_as_recipe_context(self):
        env = select_recipe_envelope(
            context(
                BatteryChemistry.AGM,
                ChargeIntent.RECOVERY,
                BatteryCondition.REHYDRATED,
            )
        )
        self.assertEqual(env.condition, BatteryCondition.REHYDRATED)
        self.assertIn("rehydrated", env.rationale.lower())


if __name__ == "__main__":
    unittest.main()
