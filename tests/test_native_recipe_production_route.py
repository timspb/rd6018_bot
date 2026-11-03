"""Production tick chooses native AUTO route and preserves unchanged fallback.

Stop execution at the exact dispatch boundary; no telemetry/hardware actions.
"""
import types
import unittest
from unittest.mock import AsyncMock, patch

from application.charge_session_tick import _run_charge_session_tick_body
from runtime.charge.programs.native_recipe_runtime import native_recipe_id_for_host
from runtime.charge.programs.native_recipe_catalog import native_recipes


class _DispatchReached(Exception):
    pass


class NativeRecipeProductionRouteTests(unittest.IsolatedAsyncioTestCase):
    def test_all_native_session_ids_and_manual_fallback(self):
        for entry in native_recipes():
            host = types.SimpleNamespace(battery_type=entry.profile,
                                         _v2_intent=entry.intent)
            self.assertEqual(native_recipe_id_for_host(host), entry.recipe_id)
        for profile, intent in (
            ("Custom", "normal"), ("EFB", None), ("EFB", "manual"),
            ("Other", "recovery"), ("AGM", "recovered-invalid"),
        ):
            host = types.SimpleNamespace(battery_type=profile,
                                         _v2_intent=intent)
            self.assertIsNone(native_recipe_id_for_host(host))

    async def _check_route(self, *, profile, intent, use_native):
        host = types.SimpleNamespace(
            battery_type=profile, _v2_intent=intent,
            current_stage="STAGE_MAIN", _mix_active_authority=None,
            STAGE_MIX="STAGE_MIX", STAGE_IDLE="STAGE_IDLE",
            STAGE_SAFE_WAIT="STAGE_SAFE_WAIT", STAGE_COOLING="STAGE_COOLING",
            _v2_target_voltage_v=14.5,
        )
        with patch(
            "application.charge_session_tick.refresh_pre_tick_diagnostics",
            new_callable=AsyncMock,
        ), patch(
            "runtime.charge.programs.native_recipe_runtime.run_native_recipe_tick",
            new_callable=AsyncMock, side_effect=_DispatchReached,
        ) as native, patch(
            "application.charge_session_tick.run_charge_stage_tick",
            new_callable=AsyncMock, side_effect=_DispatchReached,
        ) as original:
            with self.assertRaises(_DispatchReached):
                await _run_charge_session_tick_body(
                    host, 14.5, 0.5, 25.0, True, 2.0,
                    output_is_on=True, is_cc=False, manual_active=False,
                )
            if use_native:
                native.assert_awaited_once()
                self.assertEqual(native.await_args.args[0],
                                 native_recipe_id_for_host(host))
                original.assert_not_awaited()
            else:
                original.assert_awaited_once()
                native.assert_not_awaited()

    async def test_production_dispatches_auto_recipes_but_not_manual(self):
        for entry in native_recipes():
            with self.subTest(recipe=entry.recipe_id):
                await self._check_route(
                    profile=entry.profile, intent=entry.intent, use_native=True)
        await self._check_route(profile="EFB", intent="manual", use_native=False)
        await self._check_route(profile="Custom", intent="normal", use_native=False)

