"""Hardware-inert tests for detached emergency OFF and native lease disarm."""
import asyncio
from types import SimpleNamespace
import unittest

from tools.acceptance_guard.hardware_off import HardwareOffAdapter


class ButtonInfo:
    def __init__(self, object_id, key, device_id):
        self.object_id, self.key, self.device_id = object_id, key, device_id


def meta(age=0.1, status="ok"):
    return {key: {"status": status, "age_s": age} for key in (
        "output_state_code_v2", "voltage", "current", "protection_code",
        "ovp_readback_v2", "ocp_readback_v2")}


class FakeHA:
    def __init__(self, events, mode): self.events, self.mode = events, mode
    async def discover(self): self.events.append("ha.discover")
    async def disable_output(self):
        self.events.append("ha.off")
        if self.mode == "ha-command-fails": raise RuntimeError("HA command")
    async def get_live_values(self):
        self.events.append("ha.read")
        if self.mode == "ha-read-fails": raise RuntimeError("HA read")
        return dict(output_state_code_v2=0, voltage=0, current=0, protection_code=0,
                    ovp_readback_v2=14.07, ocp_readback_v2=.2, _meta=meta())
    async def close(self): self.events.append("ha.close")


class FakeNative:
    def __init__(self, events, mode):
        self.events, self.mode = events, mode
        self.armed = mode != "already-disarmed"
        self.generation = 7
        self.entities = [ButtonInfo("safety_lease_disarm", 42, 9)]
        self.client = SimpleNamespace(button_command=self.button)
    def button(self, key, device):
        self.events.append(("button", key, device))
        if self.mode == "ambiguous-ack": return
        self.armed = False
        # Actual ESP firmware disarm leaves generation unchanged.
    async def discover(self): self.events.append("native.discover"); return self.entities
    async def disable_output(self): self.events.append("native.off")
    async def get_live_values(self):
        self.events.append("native.read")
        if self.mode in ("native-read-fails", "stale-heartbeat"):
            status, age = ("unknown", None) if self.mode == "native-read-fails" else ("ok", 90)
        else: status, age = "ok", .1
        return dict(output_state_code_v2=0, voltage=0, current=0, protection_code=0,
                    ovp_readback_v2=14.07, ocp_readback_v2=.2,
                    _meta=meta(age if age is not None else 0, status))
    async def get_entity_state(self, object_id):
        self.events.append(("state", object_id))
        data = {"safety_lease_armed": self.armed,
                "safety_lease_tripped": False, "safety_boot_quarantine": False,
                "safety_lease_generation": self.generation, "safety_modbus_age": 1.0}
        value = data[object_id]
        return value, {"status": "ok", "age_s": .1}
    async def close(self): self.events.append("native.close")


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    def make(self, mode="ok", **kwargs):
        self.events = []
        config = SimpleNamespace(transports={"ha102": object(), "esp128": object()}, rd=object())
        adapter = HardwareOffAdapter(config=config,
            ha_factory=lambda *_: FakeHA(self.events, mode),
            native_factory=lambda *_: FakeNative(self.events, mode), **kwargs)
        return adapter

    async def test_off_proof_then_exactly_one_native_disarm(self):
        proof = await self.make().run()
        self.assertTrue(proof.ha_off and proof.native_off and proof.protection_normal and proof.lease_disarmed)
        self.assertLess(self.events.index("ha.off"), self.events.index("native.off"))
        self.assertLess(self.events.index("native.off"), self.events.index(("button", 42, 9)))
        self.assertEqual(self.events.count(("button", 42, 9)), 1)

    async def test_already_disarmed_is_idempotent_and_does_not_press_button(self):
        proof = await self.make("already-disarmed").run()
        self.assertTrue(proof.lease_disarmed)
        self.assertFalse(any(isinstance(item, tuple) and item[:1] == ("button",) for item in self.events))

    async def test_failed_ha_command_still_attempts_native_off_and_requires_proof(self):
        # Failed ACK does not prevent success when both fresh independent
        # physical reports prove OFF and edge disarm subsequently verifies.
        await self.make("ha-command-fails").run()
        self.assertIn("ha.off", self.events)
        self.assertIn("native.off", self.events)

    async def test_stale_heartbeat_fails_before_disarm(self):
        with self.assertRaisesRegex(RuntimeError, "verified-OFF"):
            await self.make("stale-heartbeat", timeout_s=.35, phase_timeout_s=.1).run()
        self.assertFalse(any(isinstance(item, tuple) and item[:1] == ("button",) for item in self.events))

    async def test_native_read_failure_fails_closed(self):
        with self.assertRaises(RuntimeError):
            await self.make("native-read-fails", timeout_s=.35, phase_timeout_s=.1).run()
        self.assertNotIn(("button", 42, 9), self.events)

    async def test_ambiguous_disarm_ack_is_not_reported_as_pass(self):
        with self.assertRaisesRegex(RuntimeError, "ambiguous"):
            await self.make("ambiguous-ack").run()
        # Ambiguous command is never blindly retried; containment remains OFF-only.
        self.assertEqual(self.events.count(("button", 42, 9)), 1)
        self.assertGreaterEqual(self.events.count("native.off"), 2)

    async def test_phase_timer_expires_closed(self):
        adapter = self.make(timeout_s=.2, phase_timeout_s=.01)
        class SlowHA(FakeHA):
            async def get_live_values(self):
                await asyncio.sleep(.1)
                return await super().get_live_values()
        adapter.ha_factory = lambda *_: SlowHA(self.events, "ok")
        with self.assertRaisesRegex(RuntimeError, 'verified-OFF'): await adapter.run()

    async def test_no_on_or_setpoint_surface_is_used(self):
        await self.make().run()
        self.assertFalse(any("enable" in str(event).lower() or "set_voltage" in str(event).lower()
                             or "set_current" in str(event).lower() for event in self.events))


if __name__ == "__main__": unittest.main()
