import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class V3LegacyInventoryTests(unittest.TestCase):
    def test_production_has_single_polling_owner_and_single_telegram_construction(self):
        legacy = (ROOT / "bot_legacy.py").read_text(encoding="utf-8")
        adapter = (ROOT / "telegram" / "runtime.py").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"\bdp\.start_polling\s*\(", legacy)), 1)
        self.assertEqual(len(re.findall(r"\bBot\s*\(", adapter)), 1)
        self.assertEqual(len(re.findall(r"\bDispatcher\s*\(", adapter)), 1)

    def test_bot_entrypoint_does_not_execute_legacy_module_as_a_second_process(self):
        source = (ROOT / "bot.py").read_text(encoding="utf-8")
        self.assertIn("import bot_legacy as _legacy", source)
        self.assertIn("await _legacy_main()", source)
        self.assertEqual(len(re.findall(r"asyncio\.run\(main\(\)\)", source)), 1)

    def test_inventory_documents_legacy_import_as_current_blocker(self):
        text = (ROOT / "docs" / "V3_LEGACY_RUNTIME_INVENTORY.md").read_text(encoding="utf-8")
        self.assertIn("legacy production import is confirmed", text)
        self.assertIn("ACTIVE remains fail-closed by default", text)


if __name__ == "__main__":
    unittest.main()
