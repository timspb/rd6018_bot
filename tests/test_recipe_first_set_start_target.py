import tempfile
import types
import unittest

from pb_domain import BatteryCondition, ChargeIntent
from safe_output import EnableResult
from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.charge.programs.recipe_library import RecipeLibrary
from application.start_transaction_service import start_profile_transactional
from test_start_transaction_service import FakeApp, FakeMessage


class FirstSetAtStartTests(unittest.IsolatedAsyncioTestCase):
    async def _exercise(self, *, voltage, current, ceiling_v=18.0, ceiling_i=20.0):
        with tempfile.TemporaryDirectory() as root:
            catalog = RecipeCatalog(RecipeLibrary(root, max_voltage_v=ceiling_v, max_current_a=ceiling_i))
            catalog.library.save({"id": "chosen", "version": 1, "steps": [
                {"action": "set", "params": {"voltage_v": voltage, "current_a": current},
                 "until": {"after_seconds": 30}},
                {"action": "off", "params": {}, "until": {"after_seconds": 1}},
            ]})
            app = FakeApp(EnableResult(enabled=True))
            app._user_recipe_catalog = catalog
            message = FakeMessage()
            pending = types.SimpleNamespace(
                profile="EFB", capacity_ah=70., intent=ChargeIntent.RECOVERY,
                battery_id="efb-70", condition=BatteryCondition.UNKNOWN,
                recipe_id="chosen", recipe_version=1,
            )
            result = await start_profile_transactional(app, message, pending)
            if result:
                from runtime.charge.programs.recipe_runner_store import load_runner
                binding = app.charge_controller._existing_recipe_execution_binding
                app.test_initial_runner_state = load_runner(binding.state_path, binding.session.recipe)
            return app, message, result

    async def test_initial_set_is_used_by_physical_enable_not_profile(self):
        app, msg, result = await self._exercise(voltage=13.8, current=1.2)
        self.assertTrue(result, msg.answers)
        self.assertAlmostEqual(app.hass.enable_kwargs["voltage_v"], 13.8)
        self.assertAlmostEqual(app.hass.enable_kwargs["current_a"], 1.2)
        # First recipe SET programs V/I only: routine OVP/OCP programming
        # was deliberately removed. The existing Output-ON boundary separately
        # clears stale nonzero protection registers unless explicitly requested.
        self.assertIsNone(app.hass.enable_kwargs["ovp_v"])
        self.assertIsNone(app.hass.enable_kwargs["ocp_a"])
        binding = app.charge_controller._existing_recipe_execution_binding
        self.assertEqual(binding.session.recipe.recipe_id, "chosen")
        self.assertEqual(binding.session.recipe.steps[0]["params"]["voltage_v"], 13.8)
        self.assertIsNotNone(binding.session.state.step)
        self.assertEqual(binding.session.state.step.step_index, 0)
        self.assertIsNone(binding.session.state.pending)
        self.assertEqual(app.test_initial_runner_state, binding.session.state)
        from runtime.charge.programs.recipe_runner import tick
        first_tick = tick(binding.session.recipe, binding.session.state,
                          now_s=binding.session.state.step.entered_at_s + 1,
                          measurements={"voltage": 13.8, "current": 0.1})
        self.assertIsNone(first_tick.command, "first tick must not replay verified SET")
        self.assertIn("USER_RECIPE_FIRST_SET=13.800V,1.200A", app.events[-1][-1])
        self.assertIn("Первый SET рецепта: 13.80 В / 1.20 А", msg.answers[-1][0])

    async def test_runner_persistence_failure_contained_by_verified_off(self):
        from unittest.mock import AsyncMock, patch
        with patch(
            "runtime.charge.programs.recipe_runner_store.save_runner",
            side_effect=OSError("test write failed"),
        ), patch(
            "application.start_transaction_service._confirm_failed_start_is_off",
            new_callable=AsyncMock, return_value=True,
        ) as off:
            app, msg, result = await self._exercise(voltage=13.8, current=1.2)
        self.assertFalse(result)
        self.assertTrue(app.charge_controller.stopped)
        self.assertIsNone(getattr(app.charge_controller,
                                  "_existing_recipe_execution_binding", None))
        off.assert_awaited_once()
        self.assertIn("Output OFF подтверждён", msg.answers[-1][0])

    async def test_runner_persistence_failure_unverified_off_reports_risk(self):
        from unittest.mock import AsyncMock, patch
        with patch(
            "runtime.charge.programs.recipe_runner_store.save_runner",
            side_effect=OSError("test write failed"),
        ), patch(
            "application.start_transaction_service._confirm_failed_start_is_off",
            new_callable=AsyncMock, return_value=False,
        ):
            app, msg, result = await self._exercise(voltage=13.8, current=1.2)
        self.assertFalse(result)
        self.assertFalse(app.charge_controller.stopped)
        self.assertIsNotNone(app.charge_controller._existing_recipe_execution_binding)
        self.assertIn("persistence failed", app.charge_controller._recipe_tick_fault)
        from application.charge_session_tick import run_charge_session_tick
        from unittest.mock import patch, AsyncMock
        with patch("application.recipe_existing_session.advance_in_existing_session",
                   new_callable=AsyncMock) as advance:
            self.assertEqual(
                await run_charge_session_tick(
                    app.charge_controller, 13.8, 0.1, 25.0, True, 0.0
                ), {}
            )
            advance.assert_not_awaited()
        self.assertIn("не подтверждён", msg.answers[-1][0])

    async def test_voltage_exceeds_active_battery_envelope_no_enable(self):
        app, msg, result = await self._exercise(voltage=17.0, current=1.2)
        self.assertFalse(result)
        self.assertFalse(app.charge_controller.is_active)
        self.assertIsNone(app.hass.enable_kwargs)
        self.assertIn("ceiling", msg.answers[-1][0])

    async def test_current_cannot_be_silently_capped_at_first_set(self):
        app, msg, result = await self._exercise(voltage=13.8, current=13.0)
        self.assertFalse(result)
        self.assertFalse(app.charge_controller.is_active)
        self.assertIsNone(app.hass.enable_kwargs)
        self.assertIn("current limit", msg.answers[-1][0])

