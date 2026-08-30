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
    def test_normal_preserves_full_auto_hv_while_diagnostic_is_non_hv(self):
        normal = select_recipe_envelope(
            context(BatteryChemistry.AGM, ChargeIntent.NORMAL)
        )
        diagnostic = select_recipe_envelope(
            context(BatteryChemistry.AGM, ChargeIntent.DIAGNOSTIC)
        )
        recovery = select_recipe_envelope(
            context(BatteryChemistry.AGM, ChargeIntent.RECOVERY)
        )
        self.assertEqual(normal.voltage_ceiling_v, 16.3)
        self.assertEqual(recovery.voltage_ceiling_v, 16.3)
        self.assertEqual(diagnostic.voltage_ceiling_v, 15.0)
        self.assertTrue(normal.allows_voltage(16.3))
        self.assertFalse(diagnostic.allows_voltage(16.3))

    def test_efb_normal_allows_standard_16_5_mix_not_17_5(self):
        normal = select_recipe_envelope(
            context(BatteryChemistry.EFB, ChargeIntent.NORMAL)
        )
        self.assertEqual(normal.voltage_ceiling_v, 16.5)
        self.assertTrue(normal.allows_voltage(16.5))
        self.assertFalse(normal.allows_voltage(17.5))

    def test_efb_expert_flag_does_not_create_unsupported_17_5_envelope(self):
        ordinary = select_recipe_envelope(
            context(BatteryChemistry.EFB, ChargeIntent.CONDITIONING),
            expert_high_voltage=False,
        )
        expert_flagged = select_recipe_envelope(
            context(BatteryChemistry.EFB, ChargeIntent.CONDITIONING),
            expert_high_voltage=True,
        )
        self.assertEqual(ordinary.voltage_ceiling_v, 16.5)
        self.assertEqual(expert_flagged.voltage_ceiling_v, 16.5)
        self.assertFalse(expert_flagged.expert_authorized)
        self.assertIn("no generic expert extension", expert_flagged.rationale.lower())
        self.assertFalse(expert_flagged.allows_voltage(17.2))

    def test_generic_pb_hv_current_envelope_matches_max_implemented_mix_rate(self):
        for chemistry in (
            BatteryChemistry.AGM,
            BatteryChemistry.EFB,
            BatteryChemistry.CA_CA,
            BatteryChemistry.FLOODED,
        ):
            env = select_recipe_envelope(
                context(chemistry, ChargeIntent.CONDITIONING, capacity=100),
                expert_high_voltage=True,
            )
            self.assertAlmostEqual(env.hv_current_limit_a, 3.0)

    def test_current_limits_are_capacity_relative_and_hardware_capped(self):
        efb = select_recipe_envelope(
            context(BatteryChemistry.EFB, ChargeIntent.CONDITIONING, capacity=100),
            expert_high_voltage=True,
        )
        self.assertAlmostEqual(efb.main_current_limit_a, 10.0)
        self.assertAlmostEqual(efb.hv_current_limit_a, 3.0)
        huge = select_recipe_envelope(
            context(BatteryChemistry.EFB, ChargeIntent.CONDITIONING, capacity=500),
            expert_high_voltage=True,
        )
        self.assertEqual(huge.main_current_limit_a, 12.0)
        self.assertEqual(huge.hv_current_limit_a, 12.0)

    def test_custom_can_still_use_explicit_outer_17_5_ceiling(self):
        custom = select_recipe_envelope(
            context(BatteryChemistry.CUSTOM, ChargeIntent.CONDITIONING),
            expert_high_voltage=True,
            custom_voltage_ceiling_v=17.5,
        )
        self.assertEqual(custom.voltage_ceiling_v, 17.5)
        self.assertTrue(custom.expert_authorized)

    def test_rehydrated_state_is_context_only_not_transition_override(self):
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
