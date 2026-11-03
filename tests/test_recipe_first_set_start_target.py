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
            return app, message, result

    async def test_initial_set_is_used_by_physical_enable_not_profile(self):
        app, msg, result = await self._exercise(voltage=13.8, current=1.2)
        self.assertTrue(result, msg.answers)
        self.assertAlmostEqual(app.hass.enable_kwargs["voltage_v"], 13.8)
        self.assertAlmostEqual(app.hass.enable_kwargs["current_a"], 1.2)
        self.assertAlmostEqual(app.hass.enable_kwargs["ovp_v"], 13.9)
        self.assertAlmostEqual(app.hass.enable_kwargs["ocp_a"], 1.3)
        binding = app.charge_controller._existing_recipe_execution_binding
        self.assertEqual(binding.session.recipe.recipe_id, "chosen")
        self.assertEqual(binding.session.recipe.steps[0]["params"]["voltage_v"], 13.8)
        self.assertIn("USER_RECIPE_FIRST_SET=13.800V,1.200A", app.events[-1][-1])
        self.assertIn("Первый SET рецепта: 13.80 В / 1.20 А", msg.answers[-1][0])

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

