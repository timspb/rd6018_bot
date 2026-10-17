"""D107: both declared physical routes end at one ESP; direct route wins."""
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PHYSICAL = ROOT / "config" / "physical"


class NativePriorityConfigTests(unittest.TestCase):
    def test_direct_native_wins_both_connector_and_transport_declarations(self):
        connectors = yaml.safe_load((PHYSICAL / "connectors.yaml").read_text())
        transports = yaml.safe_load((PHYSICAL / "transports.yaml").read_text())
        self.assertEqual("esp_direct", connectors["default_connector"])
        self.assertEqual("esp128", transports["default_transport"])
        direct = connectors["connectors"]["esp_direct"]
        via_ha = connectors["connectors"]["ha_esp"]
        self.assertTrue(direct["enabled"])
        self.assertTrue(via_ha["enabled"])
        self.assertEqual("esp_direct", direct["profile"])
        self.assertEqual("ha_esp", via_ha["profile"])
        self.assertLess(direct["priority"], via_ha["priority"])
        native = transports["transports"]["esp128"]
        ha = transports["transports"]["ha102"]
        self.assertTrue(native["enabled"])
        self.assertTrue(ha["enabled"])
        self.assertLess(native["priority"], ha["priority"])
        # This is a priority declaration only; it must not authorize output.
        self.assertEqual("esphome", yaml.safe_load(
            (PHYSICAL / "esp128.yaml").read_text())["type"])
        self.assertEqual("home_assistant", yaml.safe_load(
            (PHYSICAL / "ha102.yaml").read_text())["type"])


if __name__ == "__main__":
    unittest.main()
