import unittest

from legacy_recipe_adapter import authorize_legacy_target, build_legacy_charge_context
from pb_domain import BatteryCondition, ChargeIntent
from recipe_output import enable_authorized_recipe_target
from safe_output import EnableResult


class FakeAdapter:
    def __init__(self, result=None):
        self.calls = []
        self.result = result or EnableResult(enabled=True)
    async def safe_enable_output(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class RecipeOutputTests(unittest.IsolatedAsyncioTestCase):
    async def test_diagnostic_denied_hv_recipe_never_touches_hardware(self):
        context = build_legacy_charge_context(
            profile="AGM", capacity_ah=70, battery_id="agm-1",
            intent=ChargeIntent.DIAGNOSTIC, condition=BatteryCondition.HEALTHY,
        )
        auth = authorize_legacy_target(context, stage="Mix Mode", target_voltage_v=16.3, target_current_a=2.0)
        adapter = FakeAdapter()
        result = await enable_authorized_recipe_target(adapter, auth)
        self.assertFalse(result.enabled)
        self.assertEqual(adapter.calls, [])
        self.assertIn("authorization denied", result.reason)

    async def test_agm_normal_standard_mix_uses_protected_output_transaction(self):
        context = build_legacy_charge_context(
            profile="AGM", capacity_ah=70, battery_id="agm-1", intent=ChargeIntent.NORMAL,
        )
        auth = authorize_legacy_target(context, stage="Mix Mode", target_voltage_v=16.3, target_current_a=2.0)
        adapter = FakeAdapter()
        result = await enable_authorized_recipe_target(adapter, auth)
        self.assertTrue(result.enabled)
        self.assertEqual(len(adapter.calls), 1)
        self.assertAlmostEqual(adapter.calls[0]["recipe_voltage_ceiling_v"], 16.3)

    async def test_agm_recovery_uses_envelope_and_protection_margins(self):
        context = build_legacy_charge_context(profile="AGM", capacity_ah=70, battery_id="agm-1", intent=ChargeIntent.RECOVERY)
        auth = authorize_legacy_target(context, stage="Mix Mode", target_voltage_v=16.3, target_current_a=2.0)
        adapter = FakeAdapter()
        result = await enable_authorized_recipe_target(adapter, auth)
        self.assertTrue(result.enabled)
        call = adapter.calls[0]
        self.assertAlmostEqual(call["voltage_v"], 16.3)
        self.assertAlmostEqual(call["current_a"], 2.0)
        self.assertAlmostEqual(call["ovp_v"], 16.4)
        self.assertAlmostEqual(call["ocp_a"], 2.1)

    async def test_efb_expert_17_5_is_rejected_before_hardware(self):
        context = build_legacy_charge_context(
            profile="EFB", capacity_ah=70, battery_id="efb-1",
            intent=ChargeIntent.CONDITIONING, condition=BatteryCondition.REHYDRATED,
        )
        auth = authorize_legacy_target(context, stage="conditioning", target_voltage_v=17.5, target_current_a=3.0, expert_high_voltage=True)
        adapter = FakeAdapter()
        result = await enable_authorized_recipe_target(adapter, auth)
        self.assertFalse(result.enabled)
        self.assertEqual(adapter.calls, [])
        self.assertIn("authorization denied", result.reason)
        self.assertIn("voltage ceiling", result.reason)

    async def test_hardware_safety_rejection_is_returned_to_caller(self):
        context = build_legacy_charge_context(profile="EFB", capacity_ah=70, battery_id="efb-1", intent=ChargeIntent.RECOVERY)
        auth = authorize_legacy_target(context, stage="Main Charge", target_voltage_v=14.8, target_current_a=7.0)
        adapter = FakeAdapter(EnableResult(enabled=False, detail="battery_too_hot"))
        result = await enable_authorized_recipe_target(adapter, auth)
        self.assertFalse(result.enabled)
        self.assertIsNotNone(result.hardware_result)
        self.assertIn("battery_too_hot", result.reason)


if __name__ == "__main__":
    unittest.main()
