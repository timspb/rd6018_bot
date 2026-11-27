import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from aiogram.enums import ParseMode
from pb_domain import ChargeIntent, BatteryCondition
from runtime.safety.output_policy import EnableResult
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
            port_patch = patch(
                "application.start_transaction_service.get_or_create_execution_port",
                side_effect=lambda current_app: current_app.execution_port,
            )
            port_patch.start()
            self.addCleanup(port_patch.stop)
            app._user_recipe_catalog = catalog
            msg = FakeMessage()
            pending = types.SimpleNamespace(
                profile="EFB", capacity_ah=70., intent=ChargeIntent.RECOVERY,
                battery_id="efb-70", condition=BatteryCondition.UNKNOWN,
                recipe_id="draft_test", recipe_version=1,
            )
            with patch("runtime.charge.persistence.SESSION_FILE", str(Path(root) / "charge_session.json")):
                result = await start_profile_transactional(app, msg, pending)
            self.assertFalse(result)
            self.assertFalse(app.charge_controller.started)
            self.assertIsNone(app.hass.enable_kwargs)
            self.assertEqual(app.execution_port.off_calls, 0)
            self.assertIn("SET", msg.answers[-1][0])
            self.assertTrue(msg.answers[-1][0].startswith(
                "❌ Рецепт не готов к START:"))
            self.assertEqual(msg.answers[-1][1].get("parse_mode"), ParseMode.HTML)
            self.assertEqual(catalog.library.versions("draft_test"), (1,))
