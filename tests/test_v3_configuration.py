import tempfile
import unittest
import os
from pathlib import Path

from runtime.config import load_config, load_yaml
from runtime.config.validation import validate_rd


class V3ConfigurationTests(unittest.TestCase):
    def test_repository_config_loads_without_secrets(self):
        os.environ.setdefault("HA_URL", "http://127.0.0.1:8123")
        os.environ.setdefault("ESPHOME_API_HOST", "127.0.0.1")
        os.environ.setdefault("ESPHOME_API_PORT", "6053")
        bundle = load_config(Path("config"))
        self.assertEqual(bundle.transports["ha102"].connection.host, "127.0.0.1")
        self.assertEqual(bundle.transports["esp128"].connection.host, "127.0.0.1")
        self.assertEqual(bundle.transports["esp128"].connection.port, 6053)
        self.assertEqual(bundle.transports["esp128"].connection.key_env, "ESPHOME_API_KEY")
        self.assertFalse(bundle.runtime["physical_execution_enabled"])

    def test_invalid_rd_range_is_clear(self):
        with self.assertRaisesRegex(ValueError, "max_current_a=200A exceeds allowed hardware range"):
            validate_rd({"max_voltage_v": 60, "max_current_a": 200, "max_power_w": 1080})

    def test_missing_required_field_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.yaml"
            path.write_text("type: esphome\nconnection:\n  host: 192.168.1.28\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "connection.port"):
                from runtime.config.loader import _connection
                _connection(load_yaml(path), "bad")

    def test_yaml_has_no_secret_values(self):
        for path in Path("config").rglob("*.yaml"):
            text = path.read_text(encoding="utf-8").lower()
            self.assertNotIn("bearer ", text)
            self.assertNotIn("api_key:", text)
            self.assertNotIn("password:", text)

