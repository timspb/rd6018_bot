import tempfile
import types
import unittest
from aiogram.enums import ParseMode
from pb_domain import ChargeIntent, BatteryCondition
from safe_output import EnableResult
from application.start_transaction_service import start_profile_transactional
from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.charge.programs.recipe_library import RecipeLibrary
from test_start_transaction_service import FakeApp, FakeMessage

class StartOffFirstGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_off_first_draft_is_denied_before_controller_or_hardware_start(self):
        with tempfile.TemporaryDirectory() as root:
            catalog = RecipeCatalog(RecipeLibrary(
                root, max_voltage_v=15.5, max_current_a=7.2
            ))
            catalog.library.save({
                "id":"draft_test", "version":1,
                "steps":[{"action":"off","params":{},"until":{"after_seconds":1}}]
            })
            app = FakeApp(EnableResult(enabled=True))
            app._user_recipe_catalog = catalog
            msg = FakeMessage()
            pending = types.SimpleNamespace(
                profile="EFB", capacity_ah=70., intent=ChargeIntent.RECOVERY,
                battery_id="efb-70", condition=BatteryCondition.UNKNOWN,
                recipe_id="draft_test", recipe_version=1,
            )
            result = await start_profile_transactional(app, msg, pending)
            self.assertFalse(result)
            self.assertFalse(app.charge_controller.started)
            self.assertIsNone(app.hass.enable_kwargs)
            self.assertEqual(app.hass.turn_off_calls, 0)
            self.assertIn("SET", msg.answers[-1][0])
            self.assertEqual(catalog.library.versions("draft_test"), (1,))