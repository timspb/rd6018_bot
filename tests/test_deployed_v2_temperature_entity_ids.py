import unittest

from config import ENTITY_MAP
from rd6018_telemetry import canonicalize_live


class DeployedV2TemperatureEntityIdTests(unittest.TestCase):
    def test_deployed_v2_temperature_entity_ids_are_exact(self):
        self.assertEqual(
            ENTITY_MAP["temp_ext_v2"],
            "sensor.rd6018_rd_6018_temperature_external_v2",
        )
        self.assertEqual(
            ENTITY_MAP["temp_int_v2"],
            "sensor.rd6018_rd_6018_temperature_internal_v2",
        )

    def test_canonical_temperature_promotes_v2_value_and_metadata(self):
        live = {
            "temp_ext": 27.0,
            "temp_ext_v2": 28.0,
            "temp_int": 31.0,
            "temp_int_v2": 32.0,
            "_meta": {
                "temp_ext": {
                    "entity_id": "sensor.rd_6018_temperature_external",
                    "status": "ok",
                    "last_reported": "2026-09-03T02:13:15+00:00",
                },
                "temp_ext_v2": {
                    "entity_id": "sensor.rd6018_rd_6018_temperature_external_v2",
                    "status": "ok",
                    "last_reported": "2026-09-03T02:14:11+00:00",
                },
                "temp_int": {
                    "entity_id": "sensor.rd_6018_temperature",
                    "status": "ok",
                    "last_reported": "2026-09-03T02:13:07+00:00",
                },
                "temp_int_v2": {
                    "entity_id": "sensor.rd6018_rd_6018_temperature_internal_v2",
                    "status": "ok",
                    "last_reported": "2026-09-03T02:14:12+00:00",
                },
            },
        }

        canonicalize_live(live)

        self.assertEqual(live["temp_ext"], 28.0)
        self.assertEqual(live["temp_int"], 32.0)
        self.assertEqual(live["_meta"]["temp_ext"]["source_key"], "temp_ext_v2")
        self.assertEqual(live["_meta"]["temp_int"]["source_key"], "temp_int_v2")
        self.assertEqual(
            live["_meta"]["temp_ext"]["entity_id"],
            "sensor.rd6018_rd_6018_temperature_external_v2",
        )
        self.assertEqual(
            live["_meta"]["temp_int"]["entity_id"],
            "sensor.rd6018_rd_6018_temperature_internal_v2",
        )


if __name__ == "__main__":
    unittest.main()
