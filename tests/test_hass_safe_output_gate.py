"""HassClient is a transport adapter; Safety policy belongs to the runtime guard."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from config import ENTITY_MAP
from hass_api import HassClient


def live_state():
    stamp = datetime.now(timezone.utc).isoformat()
    keys = ("battery_voltage", "voltage", "current", "temp_ext", "temp_int", "switch",
            "protection_code", "set_voltage_readback_v2", "set_current_readback_v2")
    return {
        "battery_voltage": 12.4, "voltage": 0.0, "current": 0.0,
        "temp_ext": 25.0, "temp_int": 32.0, "switch": "off",
        "set_voltage": 16.3, "set_current": 2.0,
        "set_voltage_readback_v2": 16.3, "set_current_readback_v2": 2.0,
        "protection_code": 0,
        "_meta": {key: {"status": "ok", "last_reported": stamp,
                        "last_updated": stamp} for key in keys},
    }


class FakeHassClient(HassClient):
    def __init__(self):
        super().__init__("http://127.0.0.1:8123", token="test")
        self.live = live_state()
        self.service_calls = []

    async def set_value(self, entity_id, value):
        pairs = {
            ENTITY_MAP["set_voltage"]: ("set_voltage", "set_voltage_readback_v2"),
            ENTITY_MAP["set_current"]: ("set_current", "set_current_readback_v2"),
        }
        pair = pairs.get(entity_id)
        if pair is None:
            return False
        for key in pair:
            self.live[key] = float(value)
        stamp = datetime.now(timezone.utc).isoformat()
        self.live["_meta"][pair[1]] = {
            "status": "ok", "last_reported": stamp, "last_updated": stamp,
        }
        return True

    async def get_all_live(self):
        return dict(self.live)

    async def _switch_service(self, service, entity_id=None):
        self.service_calls.append(service)
        if service == "turn_on":
            self.live.update(switch="on", voltage=self.live["set_voltage"],
                             current=self.live["set_current"])
        elif service == "turn_off":
            self.live.update(switch="off", voltage=0.0, current=0.0)
        return True


class HassTransportBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_turn_on_dispatches_raw_transport_command_without_safety_policy(self):
        client = FakeHassClient()
        self.assertTrue(await client.turn_on())
        self.assertEqual(client.service_calls, ["turn_on"])
        self.assertEqual(client.live["switch"], "on")

    async def test_turn_off_dispatches_once_without_owning_readback_confirmation(self):
        client = FakeHassClient()
        self.assertTrue(await client.turn_off())
        self.assertEqual(client.service_calls, ["turn_off"])
        self.assertEqual(client.live["switch"], "off")

    async def test_numeric_writes_are_transport_only(self):
        client = FakeHassClient()
        self.assertTrue(await client.set_voltage(16.3))
        self.assertTrue(await client.set_current(2.0))
        self.assertEqual(client.live["set_voltage"], 16.3)
        self.assertEqual(client.live["set_current"], 2.0)

    async def test_hass_client_exposes_no_safety_supervisor_or_safe_enable_api(self):
        client = FakeHassClient()
        self.assertFalse(hasattr(client, "_safety_supervisor"))
        self.assertFalse(hasattr(client, "safe_enable_output"))
        self.assertFalse(hasattr(client, "verify_live_programming"))
        self.assertFalse(hasattr(client, "wait_for_output_off"))


if __name__ == "__main__":
    unittest.main()
