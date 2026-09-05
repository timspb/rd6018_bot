import pathlib
import unittest
from datetime import datetime, timezone

from config import ENTITY_MAP
from rd6018_telemetry import canonicalize_live


class ProgrammedReadbackV2ContractTests(unittest.TestCase):
    EXPECTED_ENTITIES = {
        "set_voltage_readback_v2": "sensor.rd6018_rd_6018_set_voltage_readback_v2",
        "set_current_readback_v2": "sensor.rd6018_rd_6018_set_current_readback_v2",
        "ovp_readback_v2": "sensor.rd6018_rd_6018_ovp_readback_v2",
        "ocp_readback_v2": "sensor.rd6018_rd_6018_ocp_readback_v2",
    }

    def test_entity_map_keeps_writable_numbers_and_adds_read_only_v2_sources(self):
        self.assertEqual(ENTITY_MAP["set_voltage"], "number.rd_6018_output_voltage")
        self.assertEqual(ENTITY_MAP["set_current"], "number.rd_6018_output_current")
        self.assertEqual(ENTITY_MAP["ovp"], "number.rd_6018_over_voltage_protection")
        self.assertEqual(ENTITY_MAP["ocp"], "number.rd_6018_over_current_protection")
        for key, entity_id in self.EXPECTED_ENTITIES.items():
            with self.subTest(key=key):
                self.assertEqual(ENTITY_MAP[key], entity_id)

    def test_canonical_programmed_values_and_metadata_promote_v2_readback_sources(self):
        stamp = datetime.now(timezone.utc).isoformat()
        live = {
            "set_voltage": 14.0,
            "set_current": 0.1,
            "ovp": 14.1,
            "ocp": 0.2,
            "set_voltage_readback_v2": 15.1,
            "set_current_readback_v2": 0.18,
            "ovp_readback_v2": 15.3,
            "ocp_readback_v2": 0.4,
            "_meta": {},
        }
        for key in (
            "set_voltage",
            "set_current",
            "ovp",
            "ocp",
            "set_voltage_readback_v2",
            "set_current_readback_v2",
            "ovp_readback_v2",
            "ocp_readback_v2",
        ):
            live["_meta"][key] = {
                "status": "ok",
                "last_reported": stamp,
                "last_updated": stamp,
                "source_key": key,
            }
        canonicalize_live(live)
        self.assertEqual(live["set_voltage"], 15.1)
        self.assertEqual(live["set_current"], 0.18)
        self.assertEqual(live["ovp"], 15.3)
        self.assertEqual(live["ocp"], 0.4)
        self.assertEqual(live["_meta"]["set_voltage"]["source_key"], "set_voltage_readback_v2")
        self.assertEqual(live["_meta"]["set_current"]["source_key"], "set_current_readback_v2")
        self.assertEqual(live["_meta"]["ovp"]["source_key"], "ovp_readback_v2")
        self.assertEqual(live["_meta"]["ocp"]["source_key"], "ocp_readback_v2")

    def test_esphome_exposes_force_updated_read_only_register_mirrors(self):
        text = pathlib.Path("esphome/packages/rd6018_telemetry_v2.yaml").read_text(encoding="utf-8")
        expected = {
            "Set Voltage Readback V2": 8,
            "Set Current Readback V2": 9,
            "OVP Readback V2": 82,
            "OCP Readback V2": 83,
        }
        for name, address in expected.items():
            with self.subTest(name=name):
                block = text.split(f'name: "{name}"', 1)[1].split("- platform:", 1)[0]
                self.assertIn(f"address: {address}", block)
                self.assertIn("value_type: U_WORD", block)
                self.assertIn("force_update: true", block)
                self.assertIn("multiply: 0.01", block)
        self.assertNotIn('name: "Set Voltage Readback V2"\n    platform: number', text)


if __name__ == "__main__":
    unittest.main()
