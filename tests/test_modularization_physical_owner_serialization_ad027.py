"""AD027 fake-only characterization of physical OFF ownership paths."""

import asyncio
import time
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from application.execution_port import get_or_create_execution_port
from application.guard_execution_owner_lock import GuardExecutionOwnerLock
from application.operator_recovery_clearance import VerifiedOffEvidence
from runtime.safety.runtime_guard import OutputOffNotConfirmed, RuntimeSafetyGuard


def _switch_report(state, stamp=None):
    stamp = (stamp or datetime.now(timezone.utc)).isoformat()
    return {
        "switch": state,
        "_meta": {"switch": {"status": "ok", "last_reported": stamp, "last_updated": stamp}},
    }


class FakeHass:
    def __init__(self, confirm_off=True):
        self.events = []
        self.off_entered = asyncio.Event()
        self.release_off = asyncio.Event()
        self.confirm_off = confirm_off
        self.off_calls = 0
        self.on_calls = 0
        self._heartbeat_base = datetime.now(timezone.utc)
        self._heartbeat_reads = 0
        self.equal_heartbeat = False
        self._off_report_after = None
        self.live = _switch_report("off", self._heartbeat_base)

    async def get_all_live(self):
        self.events.append("live")
        if not self.equal_heartbeat:
            self._heartbeat_reads += 1
        stamp = self._heartbeat_base + timedelta(milliseconds=self._heartbeat_reads)
        if self.confirm_off:
            if self._off_report_after is not None and not self.equal_heartbeat:
                stamp = max(stamp, self._off_report_after + timedelta(milliseconds=self._heartbeat_reads))
            self.live = _switch_report("off", stamp)
        return self.live

    async def turn_off(self, entity_id=None):
        self.off_calls += 1
        self._off_report_after = datetime.now(timezone.utc) + timedelta(milliseconds=10)
        self.events.append("raw_off_enter")
        self.off_entered.set()
        await self.release_off.wait()
        self.events.append("raw_off_return")
        return True

    async def set_current(self, value):
        self.events.append(("raw_current", value))
        return True

    async def set_voltage(self, value):
        self.events.append(("raw_voltage", value))
        return True

    async def turn_on(self, entity_id=None):
        self.on_calls += 1
        self.events.append("raw_on")
        return True


class NativeFakeHass(FakeHass):
    def __init__(self, report):
        super().__init__()
        self.native_report = report

    async def get_native_physical_output_report(self):
        self.events.append("native_report")
        return self.native_report() if callable(self.native_report) else self.native_report


class PhysicalOwnerSerializationAD027Tests(unittest.IsolatedAsyncioTestCase):
    def compose(self, hass):
        app = types.SimpleNamespace(
            hass=hass,
            charge_controller=types.SimpleNamespace(is_active=False),
            _charge_notify=lambda *args, **kwargs: None,
        )
        guard = RuntimeSafetyGuard(app)
        guard.OFF_CONFIRMATION_WINDOW_S = 0.0
        guard.install()
        app.runtime_safety_guard = guard
        port = get_or_create_execution_port(app)
        self.assertIsInstance(app.guard_execution_owner_lock, GuardExecutionOwnerLock)
        self.assertIs(port._guard_owner_lock, app.guard_execution_owner_lock)
        return app, guard, port

    async def test_ordinary_off_waits_for_normal_setter_lock(self):
        hass = FakeHass()
        _, guard, port = self.compose(hass)
        hass.release_off.set()
        await port.request_verified_off()
        hass.events.clear()
        hass.release_off.clear()
        hass.off_entered.clear()

        raw_set = guard._raw_set_current
        normal_entered = asyncio.Event()
        second_started = asyncio.Event()
        release_current = asyncio.Event()
        voltage_entered = asyncio.Event()

        async def record_current(value):
            normal_entered.set()
            await release_current.wait()
            return await raw_set(value)

        raw_voltage = guard._raw_set_voltage

        async def record_voltage(value):
            voltage_entered.set()
            return await raw_voltage(value)

        guard._raw_set_current = record_current
        guard._raw_set_voltage = record_voltage
        first = asyncio.create_task(port.program_current(2.0))
        await asyncio.wait_for(normal_entered.wait(), 1)
        off_task = asyncio.create_task(port.request_verified_off())
        async def second_setter():
            second_started.set()
            return await port.program_voltage(14.2)

        second = asyncio.create_task(second_setter())
        await asyncio.wait_for(second_started.wait(), 1)
        # The second setter is queued on the same app lock while the first
        # normal setter still owns it.
        self.assertFalse(second.done())
        self.assertFalse(off_task.done())
        self.assertEqual(hass.off_calls, 1)  # only the setup OFF ran
        self.assertNotIn("raw_off_enter", hass.events)
        self.assertNotIn(("raw_voltage", 14.2), hass.events)
        release_current.set()
        await asyncio.wait_for(hass.off_entered.wait(), 1)
        hass.release_off.set()
        self.assertEqual(await asyncio.wait_for(asyncio.gather(off_task, first, second), 1), [True, True, True])
        self.assertLess(hass.events.index(("raw_current", 2.0)), hass.events.index(("raw_voltage", 14.2)))
        self.assertLess(hass.events.index(("raw_current", 2.0)), hass.events.index("raw_off_enter"))
        self.assertLess(hass.events.index("raw_off_enter"), hass.events.index("raw_off_return"))
        self.assertLess(hass.events.index("raw_off_return"), hass.events.index(("raw_voltage", 14.2)))

    async def test_real_guard_off_lock_is_distinct_and_normal_setter_enters(self):
        hass = FakeHass()
        app, guard, port = self.compose(hass)
        self.assertIsNot(app.guard_execution_owner_lock, guard._off_lock)
        raw_set = guard._raw_set_current
        normal_entered = asyncio.Event()
        release_current = asyncio.Event()

        async def record_current(value):
            normal_entered.set()
            await release_current.wait()
            return await raw_set(value)

        guard._raw_set_current = record_current
        off_task = asyncio.create_task(guard.turn_off())
        await asyncio.wait_for(hass.off_entered.wait(), 1)
        self.assertTrue(guard._off_lock.locked())
        setter_task = asyncio.create_task(port.program_current(1.5))
        await asyncio.wait_for(normal_entered.wait(), 1)
        self.assertTrue(app.guard_execution_owner_lock.locked())
        self.assertFalse(setter_task.done())
        self.assertNotIn(("raw_current", 1.5), hass.events)
        self.assertFalse(off_task.done())
        release_current.set()
        await asyncio.wait_for(setter_task, 1)
        self.assertIn(("raw_current", 1.5), hass.events)
        hass.release_off.set()
        self.assertEqual(await asyncio.wait_for(setter_task, 1), True)
        self.assertTrue(await asyncio.wait_for(off_task, 1))
        self.assertLess(hass.events.index("raw_off_enter"), hass.events.index(("raw_current", 1.5)))
        self.assertLess(hass.events.index(("raw_current", 1.5)), hass.events.index("raw_off_return"))

    async def test_uncertain_off_latches_and_fresh_switch_off_allows_guarded_on_path(self):
        hass = FakeHass(confirm_off=False)
        _, guard, port = self.compose(hass)
        guard.OFF_CONFIRMATION_WINDOW_S = 0.0
        hass.live = _switch_report("on")
        stale = hass.live

        async def stale_live():
            hass.events.append("live")
            return stale

        guard._raw_get_all_live = stale_live
        off_task = asyncio.create_task(port.request_emergency_off())
        await asyncio.wait_for(hass.off_entered.wait(), 1)
        hass.release_off.set()
        with self.assertRaises(OutputOffNotConfirmed):
            await asyncio.wait_for(off_task, 1)
        self.assertTrue(guard._off_unconfirmed)
        with self.assertRaises(OutputOffNotConfirmed):
            await guard.turn_on()
        self.assertEqual(hass.on_calls, 0)

        fresh_heartbeat_base = datetime.now(timezone.utc) + timedelta(seconds=1)
        fresh_heartbeats = iter(
            fresh_heartbeat_base + timedelta(seconds=offset)
            for offset in range(3)
        )

        async def fresh_off():
            hass.events.append("fresh_switch_off")
            # turn_on consumes one report to clear the uncertain-OFF latch,
            # then one pre-command and one post-command report. Keep their
            # heartbeats explicitly ordered so coarse Windows clock resolution
            # cannot collapse the strict post-command comparison.
            return _switch_report("off", next(fresh_heartbeats))

        async def raw_on_false(entity_id=None):
            hass.on_calls += 1
            hass.events.append("raw_on_false")
            return False

        guard._raw_get_all_live = fresh_off
        guard._raw_turn_on = raw_on_false
        # Raw ON is reached only after the fresh OFF read clears uncertainty.
        # A false verification is safe and makes the guard run its real OFF path.
        hass.release_off.set()
        self.assertFalse(await guard.turn_on())
        self.assertEqual(hass.on_calls, 1)
        self.assertFalse(guard._off_unconfirmed)

    async def test_generic_switch_acceptance_is_not_native_receipt(self):
        hass = FakeHass()
        _, _, port = self.compose(hass)
        hass.release_off.set()
        self.assertIs(await port.request_verified_off(), True)
        self.assertNotIsInstance(True, VerifiedOffEvidence)

    async def test_equal_switch_heartbeat_does_not_confirm_post_command_off(self):
        hass = FakeHass()
        hass.equal_heartbeat = True
        _, _, port = self.compose(hass)
        hass.release_off.set()
        with self.assertRaises(OutputOffNotConfirmed):
            await port.request_verified_off()

    async def test_strict_evidence_requires_fresh_native_sensorstate_report(self):
        hass = NativeFakeHass(lambda: (0, {
            "subscription_timestamp_monotonic": 100.001,
            "age_s": 0.0,
            "native_type": "SensorState",
            "status": "ok",
        }))
        _, _, port = self.compose(hass)
        hass.release_off.set()
        with patch("application.execution_port.NATIVE_OFF_EVIDENCE_TIMEOUT_S", 0.0), \
             patch("application.execution_port._time", types.SimpleNamespace(
                 monotonic=Mock(side_effect=[100.0, 100.002, 100.003]),
                 time_ns=lambda: 1,
             )):
            receipt = await port.request_verified_off_evidence()
        self.assertIsInstance(receipt, VerifiedOffEvidence)
        self.assertEqual(hass.events.count("native_report"), 1)

        stale = NativeFakeHass((0, {
            "subscription_timestamp_monotonic": 0.0,
            "age_s": 0.0,
            "native_type": "SensorState",
            "status": "ok",
        }))
        _, _, stale_port = self.compose(stale)
        stale.release_off.set()
        with patch("application.execution_port.NATIVE_OFF_EVIDENCE_TIMEOUT_S", 0.0), \
             patch("application.execution_port._time", types.SimpleNamespace(
                 monotonic=Mock(side_effect=[100.0, 100.001]),
                 time_ns=lambda: 1,
             )):
            self.assertIsNone(await stale_port.request_verified_off_evidence())

    async def test_native_callback_at_off_completion_is_rejected(self):
        hass = NativeFakeHass(lambda: (0, {
            "subscription_timestamp_monotonic": 100.0,
            "age_s": 0.0,
            "native_type": "SensorState",
            "status": "ok",
        }))
        _, _, port = self.compose(hass)
        hass.release_off.set()
        with patch("application.execution_port.NATIVE_OFF_EVIDENCE_TIMEOUT_S", 0.0), \
             patch("application.execution_port._time", types.SimpleNamespace(
                 monotonic=Mock(side_effect=[100.0, 100.001]),
                 time_ns=lambda: 1,
             )):
            self.assertIsNone(await port.request_verified_off_evidence())

    async def test_emergency_off_attempt_is_available_while_app_lock_is_held(self):
        hass = FakeHass()
        app, guard, port = self.compose(hass)
        hass.release_off.set()
        held = asyncio.Event()
        release = asyncio.Event()

        async def hold_app_lock():
            async with app.guard_execution_owner_lock:
                held.set()
                await release.wait()

        normal = asyncio.create_task(hold_app_lock())
        await asyncio.wait_for(held.wait(), 1)
        emergency = asyncio.create_task(port.request_emergency_off())
        await asyncio.wait_for(hass.off_entered.wait(), 1)
        self.assertTrue(app.guard_execution_owner_lock.locked())
        self.assertIn("raw_off_enter", hass.events)
        self.assertIs(await asyncio.wait_for(emergency, 1), True)
        release.set()
        await asyncio.wait_for(normal, 1)

    async def test_execution_port_emergency_off_uses_guard_lock_while_app_lock_is_held(self):
        hass = FakeHass()
        app, guard, port = self.compose(hass)
        app_lock_held = asyncio.Event()
        release_app_lock = asyncio.Event()

        async def hold_app_lock():
            async with app.guard_execution_owner_lock:
                app_lock_held.set()
                await release_app_lock.wait()

        owner = asyncio.create_task(hold_app_lock())
        emergency = None
        try:
            await asyncio.wait_for(app_lock_held.wait(), 1)
            emergency = asyncio.create_task(port.request_emergency_off())
            await asyncio.wait_for(hass.off_entered.wait(), 1)
            self.assertTrue(app.guard_execution_owner_lock.locked())
            self.assertTrue(guard._off_lock.locked())
            hass.release_off.set()
            self.assertIs(await asyncio.wait_for(emergency, 1), True)
            self.assertTrue(app.guard_execution_owner_lock.locked())
            self.assertIn("raw_off_return", hass.events)
        finally:
            hass.release_off.set()
            release_app_lock.set()
            if emergency is not None:
                await asyncio.gather(emergency, return_exceptions=True)
            await asyncio.wait_for(owner, 1)


if __name__ == "__main__":
    unittest.main()
