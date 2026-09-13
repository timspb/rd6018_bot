import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from config import ENTITY_MAP


class _HaState:
    def __init__(self):
        self.lock = threading.Lock()
        self.service_calls = []
        self.values = {
            ENTITY_MAP["battery_voltage"]: "12.55",
            ENTITY_MAP["voltage"]: "12.55",
            ENTITY_MAP["current"]: "0.00",
            ENTITY_MAP["power"]: "0.00",
            ENTITY_MAP["power_v2"]: "0.00",
            ENTITY_MAP["ah"]: "4.2",
            ENTITY_MAP["wh"]: "52.7",
            ENTITY_MAP["temp_int"]: "25.0",
            ENTITY_MAP["temp_ext"]: "24.5",
            ENTITY_MAP["temp_int_v2"]: "25.0",
            ENTITY_MAP["temp_ext_v2"]: "24.5",
            ENTITY_MAP["is_cv"]: "off",
            ENTITY_MAP["is_cc"]: "off",
            ENTITY_MAP["regulation_code"]: "0",
            ENTITY_MAP["protection_code"]: "0",
            ENTITY_MAP["output_state_code_v2"]: "0",
            ENTITY_MAP["battery_mode"]: "on",
            ENTITY_MAP["keypad_lock"]: "off",
            ENTITY_MAP["ovp_triggered"]: "off",
            ENTITY_MAP["ocp_triggered"]: "off",
            ENTITY_MAP["switch"]: "off",
            ENTITY_MAP["set_voltage"]: "14.80",
            ENTITY_MAP["set_current"]: "2.00",
            ENTITY_MAP["ovp"]: "14.90",
            ENTITY_MAP["ocp"]: "2.10",
            ENTITY_MAP["set_voltage_readback_v2"]: "14.80",
            ENTITY_MAP["set_current_readback_v2"]: "2.00",
            ENTITY_MAP["ovp_readback_v2"]: "14.90",
            ENTITY_MAP["ocp_readback_v2"]: "2.10",
            ENTITY_MAP["input_voltage"]: "68.0",
            ENTITY_MAP["autonomous_mode"]: "off",
            ENTITY_MAP["take_ok"]: "on",
            ENTITY_MAP["take_out"]: "off",
            ENTITY_MAP["boot_power"]: "off",
        }
        self.readback_for_number = {
            ENTITY_MAP["set_voltage"]: ENTITY_MAP["set_voltage_readback_v2"],
            ENTITY_MAP["set_current"]: ENTITY_MAP["set_current_readback_v2"],
            ENTITY_MAP["ovp"]: ENTITY_MAP["ovp_readback_v2"],
            ENTITY_MAP["ocp"]: ENTITY_MAP["ocp_readback_v2"],
        }

    @staticmethod
    def _timestamp():
        return datetime.now(timezone.utc).isoformat()

    def states_payload(self):
        with self.lock:
            now = self._timestamp()
            return [
                {
                    "entity_id": entity_id,
                    "state": state,
                    "attributes": {},
                    "last_changed": now,
                    "last_updated": now,
                    "last_reported": now,
                }
                for entity_id, state in self.values.items()
            ]

    def set_number(self, entity_id, value):
        with self.lock:
            rendered = str(float(value))
            self.values[entity_id] = rendered
            readback = self.readback_for_number.get(entity_id)
            if readback:
                self.values[readback] = rendered
            self.service_calls.append(("number.set_value", entity_id, float(value)))

    def set_switch(self, on):
        with self.lock:
            self.values[ENTITY_MAP["switch"]] = "on" if on else "off"
            self.values[ENTITY_MAP["output_state_code_v2"]] = "1" if on else "0"
            if on:
                self.values[ENTITY_MAP["voltage"]] = self.values[ENTITY_MAP["set_voltage"]]
                self.values[ENTITY_MAP["current"]] = "0.20"
                self.values[ENTITY_MAP["regulation_code"]] = "1"
                self.values[ENTITY_MAP["is_cc"]] = "on"
            else:
                self.values[ENTITY_MAP["current"]] = "0.00"
                self.values[ENTITY_MAP["regulation_code"]] = "0"
                self.values[ENTITY_MAP["is_cc"]] = "off"
                self.values[ENTITY_MAP["is_cv"]] = "off"
            self.service_calls.append(("switch.turn_on" if on else "switch.turn_off", ENTITY_MAP["switch"], None))


class _Handler(BaseHTTPRequestHandler):
    state = None

    def log_message(self, *_args):
        return

    def _json(self, status, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/api/states":
            self._json(200, self.state.states_payload())
            return
        self._json(404, {})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/api/services/number/set_value":
            self.state.set_number(body["entity_id"], body["value"])
            self._json(200, [])
            return
        if self.path == "/api/services/switch/turn_on":
            self.state.set_switch(True)
            self._json(200, [])
            return
        if self.path == "/api/services/switch/turn_off":
            self.state.set_switch(False)
            self._json(200, [])
            return
        self._json(404, {})


class RestartRestoreHaCompositionTests(unittest.TestCase):
    def setUp(self):
        self.state = _HaState()
        handler = type("BoundHandler", (_Handler,), {"state": self.state})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_deferred_managed_restore_reenergizes_through_real_hass_adapter(self):
        """A saved managed MAIN session must not become software-active/physical-OFF."""
        repo_root = Path(__file__).resolve().parents[1]
        ha_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        script = r'''
import asyncio
import json
import time

import bot
from rd_startup_authority import reconcile_startup_authority

shim = bot.main.__globals__
controller = bot.charge_controller
gate = bot.rd_startup_authority_gate

with open("charge_session.json", "w", encoding="utf-8") as handle:
    json.dump(
        {
            "profile": controller.PROFILE_CA,
            "stage": controller.STAGE_MAIN,
            "stage_start_time": time.time() - 600.0,
            "target_voltage": 14.8,
            "target_current": 2.0,
            "ah_limit": 60,
            "current_retries": 0,
            "agm_stage_idx": 0,
            "saved_at": time.time(),
        },
        handle,
    )

async def run():
    # Reproduce the real race: legacy startup asks for restore while startup
    # authority is still unresolved. The outer gate must defer, not mutate.
    ok, message = controller.try_restore_session(
        12.55,
        0.0,
        4.2,
        output_is_on=False,
        is_cv=False,
        is_cc=False,
    )
    assert ok is False and message is None
    assert gate.deferred_restore_requested
    assert controller.current_stage == controller.STAGE_IDLE

    async def recover():
        return True

    result = await reconcile_startup_authority(
        gate,
        recover,
        shim["_replay_deferred_startup_restore"],
    )
    live = await gate.guard._raw_live()
    payload = {
        "result": result,
        "stage": controller.current_stage,
        "active": bool(controller.is_active),
        "switch": str(live.get("switch", "")).lower(),
        "deferred": gate.deferred_restore_requested,
    }
    await bot.hass.close()
    print("RESULT=" + json.dumps(payload, sort_keys=True))

asyncio.run(run())
'''
        env = os.environ.copy()
        env.update(
            {
                "TG_TOKEN": "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
                "HA_URL": ha_url,
                "HA_TOKEN": "integration-test-token",
                "HA_PREFER_LOCAL": "0",
                "ALLOWED_CHAT_IDS": "1",
                # This integration proves the HA/runtime composition boundary. The
                # physical edge lease has its own dedicated contract/physical tests.
                "RD6018_EDGE_LEASE_REQUIRED": "0",
                "PYTHONPATH": str(repo_root),
            }
        )
        with tempfile.TemporaryDirectory() as workdir:
            completed = subprocess.run(
                [sys.executable, "-c", script],
                cwd=workdir,
                env=env,
                text=True,
                capture_output=True,
                timeout=30,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        result_line = next(
            line for line in completed.stdout.splitlines() if line.startswith("RESULT=")
        )
        payload = json.loads(result_line.removeprefix("RESULT="))
        self.assertEqual(payload["result"], "managed")
        self.assertEqual(payload["stage"], "Main Charge")
        self.assertTrue(payload["active"])
        self.assertFalse(payload["deferred"])
        self.assertEqual(
            payload["switch"],
            "on",
            "managed restore must not leave an active software session with physical Output OFF",
        )
        self.assertTrue(
            any(call[0] == "switch.turn_on" for call in self.state.service_calls),
            self.state.service_calls,
        )


if __name__ == "__main__":
    unittest.main()
