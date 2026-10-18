"""D111 offline contract: canonical ESPHome 2.3 HA source and fail-closed copy."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ha23_release", ROOT / "tools/rd6018_ha23_release.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class HA23ReleaseContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.t = Path(self.temp.name)
        self.stage = self.t / "stage"
        mod.stage(ROOT / "esphome", self.stage)

    def test_source_identity_and_safety_packages(self):
        record = mod.verify(self.stage)
        self.assertEqual(record["release"], "2.3-ha-canonical")
        self.assertEqual(len(record["source_files_sha256"]), 5)
        lease = (self.stage / "packages/rd6018_safety_lease.yaml").read_text()
        self.assertIn('rd6018_safety_lease_ttl_ms: "900000"', lease)
        self.assertIn('rd6018_safety_modbus_stale_ms: "20000"', lease)
        self.assertIn('switch.turn_off: rd6018_safety_output', lease)
    def test_stale_source_downgrade_blocked(self):
        p = self.stage / "rd6018.yaml"
        p.write_text(p.read_text().replace("2.3-ha-canonical", "2.0-edge-adoption"))
        with self.assertRaises(ValueError):
            mod.verify(self.stage)

    def test_corrupt_package_blocked(self):
        with (self.stage / "packages/rd6018_safety_lease.yaml").open("a") as f:
            f.write("\n# unexpected mutation\n")
        with self.assertRaises(ValueError):
            mod.verify(self.stage)

    def test_installer_preserves_secrets_and_backs_up_old_yaml(self):
        ha = self.t / "ha"
        (ha / "packages").mkdir(parents=True)
        (ha / "secrets.yaml").write_text("secret_marker: unchanged\n")
        (ha / "rd6018.yaml").write_text('esphome: {project: {version: "2.0-edge-adoption"}}\n')
        mod.install(self.stage, ha)
        self.assertEqual((ha / "secrets.yaml").read_text(), "secret_marker: unchanged\n")
        self.assertEqual(mod.verify(ha)["release"], "2.3-ha-canonical")
        backups = list((ha / "rd6018_release_backups").glob("*/rd6018.yaml.bak"))
        self.assertEqual(len(backups), 1)
        self.assertIn("2.0-edge-adoption", backups[0].read_text())

    def test_missing_ha_secrets_refused(self):
        ha = self.t / "ha"
        ha.mkdir()
        (ha / "rd6018.yaml").write_text("old")
        with self.assertRaises(ValueError):
            mod.install(self.stage, ha)

if __name__ == "__main__":
    unittest.main()
