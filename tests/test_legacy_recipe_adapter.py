import unittest

from legacy_recipe_adapter import authorize_legacy_target, build_legacy_charge_context, chemistry_for_legacy_profile
from pb_domain import BatteryChemistry, BatteryCondition, ChargeIntent


class LegacyRecipeAdapterTests(unittest.TestCase):
    def test_profile_mapping_is_explicit(self):
        self.assertEqual(chemistry_for_legacy_profile("Ca/Ca"), BatteryChemistry.CA_CA)
        self.assertEqual(chemistry_for_legacy_profile("EFB"), BatteryChemistry.EFB)
        self.assertEqual(chemistry_for_legacy_profile("AGM"), BatteryChemistry.AGM)
        with self.assertRaises(ValueError):
            chemistry_for_legacy_profile("magic")

    def test_agm_normal_allows_standard_legacy_mix_target(self):
        context = build_legacy_charge_context(
            profile="AGM", capacity_ah=70, battery_id="agm-1",
            intent=ChargeIntent.NORMAL, condition=BatteryCondition.HEALTHY,
        )
        auth = authorize_legacy_target(context, stage="Mix Mode", target_voltage_v=16.3, target_current_a=2.0)
        self.assertTrue(auth.allowed)
        self.assertEqual(auth.envelope.voltage_ceiling_v, 16.3)

    def test_agm_diagnostic_rejects_automatic_mix_target(self):
        context = build_legacy_charge_context(
            profile="AGM", capacity_ah=70, battery_id="agm-1",
            intent=ChargeIntent.DIAGNOSTIC, condition=BatteryCondition.HEALTHY,
        )
        auth = authorize_legacy_target(context, stage="Mix Mode", target_voltage_v=16.3, target_current_a=2.0)
        self.assertFalse(auth.allowed)
        self.assertEqual(auth.envelope.voltage_ceiling_v, 15.0)

    def test_agm_recovery_allows_explicit_hv_target(self):
        context = build_legacy_charge_context(
            profile="AGM", capacity_ah=70, battery_id="agm-1",
            intent=ChargeIntent.RECOVERY, condition=BatteryCondition.SULFATED_SUSPECTED,
        )
        auth = authorize_legacy_target(context, stage="Mix Mode", target_voltage_v=16.3, target_current_a=2.0)
        self.assertTrue(auth.allowed)
        self.assertEqual(auth.stage_kind, "hv")

    def test_efb_expert_flag_does_not_authorize_17_5v(self):
        context = build_legacy_charge_context(
            profile="EFB", capacity_ah=70, battery_id="efb-1",
            intent=ChargeIntent.CONDITIONING, condition=BatteryCondition.REHYDRATED,
        )
        ordinary = authorize_legacy_target(context, stage="conditioning", target_voltage_v=17.5, target_current_a=3.0, expert_high_voltage=False)
        expert = authorize_legacy_target(context, stage="conditioning", target_voltage_v=17.5, target_current_a=3.0, expert_high_voltage=True)
        self.assertFalse(ordinary.allowed)
        self.assertFalse(expert.allowed)
        self.assertEqual(expert.envelope.voltage_ceiling_v, 16.5)
        self.assertFalse(expert.envelope.expert_authorized)
        self.assertIn("voltage ceiling", expert.reason)

    def test_current_ceiling_is_stage_sensitive(self):
        context = build_legacy_charge_context(profile="EFB", capacity_ah=70, battery_id="efb-1", intent=ChargeIntent.RECOVERY)
        main = authorize_legacy_target(context, stage="Main Charge", target_voltage_v=14.8, target_current_a=7.0)
        hv = authorize_legacy_target(context, stage="Mix Mode", target_voltage_v=16.5, target_current_a=4.0)
        self.assertTrue(main.allowed)
        self.assertFalse(hv.allowed)
        self.assertIn("current ceiling", hv.reason)


if __name__ == "__main__":
    unittest.main()
