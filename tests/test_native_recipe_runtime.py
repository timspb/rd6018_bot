"""Native recipe execution must delegate to the unique production stage owner."""
import types
import unittest
from unittest.mock import AsyncMock, patch

from runtime.charge.programs.native_recipe_catalog import native_recipes
from runtime.charge.programs.native_recipe_runtime import run_native_recipe_tick


class NativeRecipeRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_twelve_variants_use_original_owner_unchanged(self):
        original_inputs = dict(
            stage_before="Main Charge", voltage=14.5, current=0.9,
            temp_ext=24.0, is_cv=True, ah=3.2, output_is_on=True,
            manual_off_active=False, is_cc=False, manual_active=False,
        )
        for entry in native_recipes():
            host = types.SimpleNamespace(
                battery_type=entry.profile, _v2_intent=entry.intent)
            expected = {"stage": "unchanged", "set_current": 0.9}
            with self.subTest(recipe=entry.recipe_id):
                with patch(
                    "application.charge_stage_tick.run_charge_stage_tick",
                    new_callable=AsyncMock, return_value=expected,
                ) as owner:
                    returned = await run_native_recipe_tick(
                        entry.recipe_id, host, **original_inputs)
                    self.assertIs(returned, expected)
                    owner.assert_awaited_once_with(host, **original_inputs)

    async def test_mismatch_is_rejected_before_any_stage_owner(self):
        with patch(
            "application.charge_stage_tick.run_charge_stage_tick",
            new_callable=AsyncMock,
        ) as owner:
            for profile, intent in (
                ("AGM", "normal"), ("EFB", "diagnostic"),
                ("Ca/Ca", None),
            ):
                host = types.SimpleNamespace(battery_type=profile,
                                             _v2_intent=intent)
                with self.assertRaises(ValueError):
                    await run_native_recipe_tick(
                        "native_ca_ca_recovery", host, stage_before="MAIN")
            owner.assert_not_awaited()

    async def test_existing_stage_dispatch_routes_to_original_owner(self):
        from contextlib import ExitStack
        from unittest.mock import AsyncMock
        stage_owners = {
            "PREP": "run_authoritative_residual_scaffold",
            "MAIN": "run_authoritative_main_scaffold",
            "DESULFATION": "run_authoritative_recovery_scaffold",
            "MIX": "run_authoritative_mix_scaffold",
            "RECOVERY_SAFE_WAIT": "run_authoritative_recovery_scaffold",
            "FINAL_SAFE_WAIT": "run_authoritative_mix_scaffold",
        }
        for entry in native_recipes():
            for name, selected in stage_owners.items():
                # DIAGNOSTIC cannot enter a new automatic HV stage; this test
                # checks routing for the variants' declared stage set only.
                if name not in entry.stages:
                    continue
                stage = ("SAFE_WAIT" if "SAFE_WAIT" in name else name)
                host = types.SimpleNamespace(
                    battery_type=entry.profile, _v2_intent=entry.intent,
                    PROFILE_CUSTOM="Custom",
                    STAGE_PREP="PREP", STAGE_MAIN="MAIN",
                    STAGE_DESULFATION="DESULFATION", STAGE_MIX="MIX",
                    STAGE_SAFE_WAIT="SAFE_WAIT", STAGE_COOLING="COOLING",
                    STAGE_IDLE="IDLE", STAGE_DONE="DONE",
                    _recovery_safe_wait=(object() if name == "RECOVERY_SAFE_WAIT" else None),
                    _final_safe_wait=(object() if name == "FINAL_SAFE_WAIT" else None),
                    _safe_wait_next_stage=None,
                )
                kwargs = dict(
                    stage_before=stage, voltage=14.5, current=1.0,
                    temp_ext=25.0, is_cv=True, ah=1.0, output_is_on=True,
                    manual_off_active=False, is_cc=False, manual_active=False,
                )
                with self.subTest(recipe=entry.recipe_id, stage=name):
                    with ExitStack() as stack:
                        mocks = {}
                        for owner in set(stage_owners.values()):
                            mocks[owner] = stack.enter_context(patch(
                                "application.charge_stage_tick." + owner,
                                new_callable=AsyncMock,
                                return_value={"owner": owner},
                            ))
                        returned = await run_native_recipe_tick(
                            entry.recipe_id, host, **kwargs)
                        self.assertEqual(returned, {"owner": selected})
                        mocks[selected].assert_awaited_once()
                        for other, mock in mocks.items():
                            if other != selected:
                                mock.assert_not_awaited()

    async def test_unknown_recipe_rejected_without_dispatch(self):
        with patch(
            "application.charge_stage_tick.run_charge_stage_tick",
            new_callable=AsyncMock,
        ) as owner:
            with self.assertRaises(KeyError):
                await run_native_recipe_tick("unknown", object())
            owner.assert_not_awaited()
