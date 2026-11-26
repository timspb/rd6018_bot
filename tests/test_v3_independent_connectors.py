import asyncio
import os
import unittest
from unittest.mock import patch
from dataclasses import replace
from types import SimpleNamespace

from runtime.config import load_config
from runtime.output.bridge import HardwareSnapshot
from runtime.physical.connectors import ConnectorSnapshotComparator, PhysicalConnectorFactory
from runtime.physical.transports.ha102 import HA102Transport
from rd6018_telemetry import telemetry_freshness


def _offline_connector_config():
    # These tests construct connectors without opening a physical connection.
    # Supply a non-routable local fixture address instead of depending on
    # the developer's ESPHOME_API_HOST environment or real node credentials.
    with patch.dict(os.environ, {
        "ESPHOME_API_HOST": "127.0.0.1", "ESPHOME_API_PORT": "6053",
    }):
        return load_config("config")


class IndependentConnectorTests(unittest.TestCase):
    def test_config_and_factory_are_independent(self):
        config = _offline_connector_config()
        ha = PhysicalConnectorFactory(config).create("ha_esp")
        esp = PhysicalConnectorFactory(config).create("esp_direct")
        self.assertEqual(ha.name, "ha_esp")
        self.assertEqual(esp.name, "esp_direct")
        self.assertIsNot(ha.transport, esp.transport)

    def test_snapshot_comparator_uses_shared_contract(self):
        left = HardwareSnapshot(
            timestamp=100,
            connection_state="connected",
            output_state=False,
            measured_voltage=0,
            measured_current=0,
            configured_voltage=13.94,
            configured_current=.55,
            temperature=31,
            battery_voltage=12,
        )
        right = replace(left, timestamp=101)
        self.assertEqual(ConnectorSnapshotComparator.compare(left, right).status, "MATCH")

    def test_connector_failure_is_isolated(self):
        config = _offline_connector_config()
        ha = PhysicalConnectorFactory(config).create("ha_esp")
        esp = PhysicalConnectorFactory(config).create("esp_direct")
        async def fail():
            ha.transport.health_check = lambda: (_ for _ in ()).throw(RuntimeError("ha down"))
            with self.assertRaises(RuntimeError):
                await ha.health_check()
            esp.transport.health_check = lambda: asyncio.sleep(0, result={"connected": True})
            self.assertTrue((await esp.health_check())["connected"])
        asyncio.run(fail())

    def test_write_surface_is_only_verified_disable(self):
        config = _offline_connector_config()
        for name in ("ha_esp", "esp_direct"):
            connector = PhysicalConnectorFactory(config).create(name)
            self.assertTrue(callable(connector.disable_output))
            self.assertTrue(callable(connector.read_snapshot))


class HA102SourceTimestampFreshnessTests(unittest.TestCase):
    NOW = 1_800_000_000.0

    def transport(self, entities):
        transport = HA102Transport.__new__(HA102Transport)
        transport.config = SimpleNamespace(entities=entities)
        return transport

    def read(self, entity_states):
        transport = self.transport({key: f"sensor.{key}" for key in entity_states})

        async def fake_get(entity_id):
            key = entity_id.removeprefix("sensor.")
            return entity_states[key]

        transport._get = fake_get
        with patch("runtime.physical.transports.ha102.time.time", return_value=self.NOW):
            return asyncio.run(transport.get_live_values())

    def test_stale_last_reported_is_not_promoted_to_fresh_by_fetch(self):
        live = self.read({
            "voltage": {
                "state": "14.2",
                "last_reported": "2020-01-01T00:00:00+00:00",
                "last_updated": "2020-01-01T00:00:00+00:00",
            },
        })

        freshness = telemetry_freshness(
            live, ["voltage"], max_age_s=20.0, now_epoch_s=self.NOW,
        )
        self.assertFalse(freshness.valid, freshness.detail)
        self.assertEqual(live["_meta"]["voltage"]["last_reported"], "2020-01-01T00:00:00+00:00")

    def test_fresh_last_reported_is_preserved_and_accepted(self):
        timestamp = "2027-01-15T08:00:00+00:00"
        live = self.read({"voltage": {"state": "14.2", "last_reported": timestamp}})

        self.assertEqual(live["_meta"]["voltage"]["last_reported"], timestamp)
        self.assertTrue(telemetry_freshness(
            live, ["voltage"], max_age_s=20.0, now_epoch_s=self.NOW,
        ).valid)

    def test_last_updated_is_timestamp_fallback(self):
        timestamp = "2027-01-15T08:00:00+00:00"
        live = self.read({"voltage": {"state": "14.2", "last_updated": timestamp}})

        self.assertEqual(live["_meta"]["voltage"]["last_updated"], timestamp)
        self.assertTrue(telemetry_freshness(
            live, ["voltage"], max_age_s=20.0, now_epoch_s=self.NOW,
        ).valid)

    def test_missing_timestamp_fails_closed(self):
        live = self.read({"voltage": {"state": "14.2"}})

        self.assertFalse(telemetry_freshness(
            live, ["voltage"], max_age_s=20.0, now_epoch_s=self.NOW,
        ).valid)

    def test_derived_aliases_inherit_source_metadata(self):
        output_ts = "2027-01-15T08:00:00+00:00"
        voltage_ts = "2027-01-15T08:00:01+00:00"
        current_ts = "2027-01-15T08:00:02+00:00"
        live = self.read({
            "output_state": {"state": "on", "last_reported": output_ts},
            "configured_voltage": {"state": "14.2", "last_reported": voltage_ts},
            "configured_current": {"state": "2.0", "last_reported": current_ts},
        })

        meta = live["_meta"]
        self.assertEqual(meta["output_state_code_v2"], meta["output_state"])
        self.assertEqual(meta["switch"], meta["output_state"])
        self.assertEqual(meta["set_voltage_readback_v2"], meta["configured_voltage"])
        self.assertEqual(meta["set_current_readback_v2"], meta["configured_current"])
