import pathlib
import unittest
from unittest.mock import patch

from battery_registry import BatteryRecord
from runtime.ui.telegram import battery_selection
from pb_domain import BatteryChemistry, BatteryIdentity, BatteryLifecycle
import production_bot_ui


class BatterySelectionRegressionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        production_bot_ui._battery_pages.clear()

    def _record(self, battery_id="Leoch_72Ah"):
        return BatteryRecord(
            identity=BatteryIdentity(battery_id, BatteryChemistry.CA_CA, 72, "Leoch", "72 Ah"),
            lifecycle=BatteryLifecycle(),
        )

    def test_battery_callback_layout_is_owned_by_telegram_component(self):
        from runtime.ui.telegram import battery_selection
        self.assertIs(production_bot_ui._battery_callback_token, battery_selection._battery_callback_token)
        self.assertIs(production_bot_ui._battery_callback_data, battery_selection._battery_callback_data)
        self.assertIs(production_bot_ui._battery_rows, battery_selection._battery_rows)

    def test_callback_encoding_preserves_previous_message_identity(self):
        import hashlib
        record = self._record("Leoch_72Ah")
        expected = hashlib.sha256(b"Leoch_72Ah").hexdigest()[:12]
        rows = production_bot_ui._battery_rows([record])
        self.assertEqual(rows[0][0].callback_data, f"v2_battery_id_{expected}")
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]), 1)

    async def test_add_flow_callback_is_durable_and_resolves_after_page_state_loss(self):
        record = self._record()
        rows = production_bot_ui._battery_rows([record])
        callback = rows[0][0].callback_data

        self.assertTrue(callback.startswith("v2_battery_id_"))
        self.assertLessEqual(len(callback.encode("utf-8")), 64)
        production_bot_ui._battery_pages.clear()
        with patch.object(battery_selection, "list_batteries", return_value=[record]):
            resolved = await production_bot_ui._resolve_battery_callback(
                callback.replace("v2_battery_", "", 1), 104
            )
        self.assertEqual(resolved.identity.battery_id, "Leoch_72Ah")

    async def test_stale_numeric_callback_reloads_registry(self):
        record = self._record()
        with patch.object(battery_selection, "list_batteries", return_value=[record]):
            resolved = await production_bot_ui._resolve_battery_callback("0", 104)
        self.assertEqual(resolved.identity.battery_id, "Leoch_72Ah")
        self.assertEqual(production_bot_ui._battery_pages[104], [record])

    def test_callback_route_excludes_add_and_start(self):
        source = pathlib.Path(__file__).parents[1].joinpath("production_bot_ui.py").read_text(encoding="utf-8")
        self.assertIn('~F.data.in_({"v2_battery_add", "v2_battery_start"})', source)
        owner_source = pathlib.Path(__file__).parents[1].joinpath(
            "runtime/ui/telegram/battery_selection.py"
        ).read_text(encoding="utf-8")
        self.assertIn("_battery_pages[user_id] = visible_records", owner_source)
        self.assertNotIn('callback_data=f"v2_battery_{idx}"', source)


if __name__ == "__main__":
    unittest.main()
