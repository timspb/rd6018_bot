"""D072 source-only shared owner admission for automatic START and manual V/I."""
import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest

from application.execution_port import get_or_create_execution_port
from application.start_transaction_service import start_profile_transactional


class FakeOwner:
    def __init__(self):
        self.events = []
        self.entered = asyncio.Event()
        self.release_voltage = asyncio.Event()

    async def set_voltage(self, value):
        self.events.append(("voltage_start", float(value)))
        self.entered.set()
        await self.release_voltage.wait()
        self.events.append(("voltage_end", float(value)))
        return True

    async def set_current(self, value):
        self.events.append(("current", float(value)))
        return True

    async def turn_off(self):
        self.events.append(("emergency_off",))
        return True


class D072OwnerTransactionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.owner = FakeOwner()
        self.app = SimpleNamespace(
            hass=self.owner,
            charge_controller=SimpleNamespace(is_active=True),
        )
        self.port = get_or_create_execution_port(self.app)

    async def test_start_preflight_waits_for_same_app_owner(self):
        answers = []
        class Message:
            from_user = None
            async def answer(self, value, **kwargs):
                answers.append(value)

        async with self.port._guard_owner_lock:
            start = asyncio.create_task(start_profile_transactional(
                self.app, Message(), None
            ))
            await asyncio.sleep(0)
            self.assertFalse(start.done())
            self.assertEqual(answers, [])
        result = await asyncio.wait_for(start, timeout=1)
        self.assertFalse(result)
        self.assertEqual(len(answers), 1)
        self.assertIn("остановите текущую программу", answers[0])

    async def test_manual_pair_keeps_v_and_i_together_against_other_normal_setters(self):
        first = asyncio.create_task(self.port.program_voltage_current(14.4, 4.0))
        await asyncio.wait_for(self.owner.entered.wait(), timeout=1)
        racing = asyncio.create_task(self.port.program_current(3.0))
        await asyncio.sleep(0)
        self.assertEqual(self.owner.events, [("voltage_start", 14.4)])
        self.assertFalse(racing.done())

        # OFF is deliberately not queued behind an ordinary setter transaction.
        self.assertTrue(await asyncio.wait_for(self.port.request_verified_off(), timeout=1))
        self.assertEqual(self.owner.events[-1], ("emergency_off",))
        self.owner.release_voltage.set()

        self.assertEqual(await asyncio.wait_for(first, timeout=1), (True, True))
        self.assertTrue(await asyncio.wait_for(racing, timeout=1))
        self.assertEqual(self.owner.events, [
            ("voltage_start", 14.4), ("emergency_off",),
            ("voltage_end", 14.4), ("current", 4.0), ("current", 3.0),
        ])

    async def test_manual_pair_uses_one_production_port_owner(self):
        self.owner.release_voltage.set()
        self.assertIs(get_or_create_execution_port(self.app), self.port)
        self.assertIs(self.app.guard_execution_owner_lock, self.port._guard_owner_lock)
        self.assertEqual(await self.port.program_voltage_current(13.8, 2.0), (True, True))
        self.assertFalse(self.port._guard_owner_lock.locked())

    def test_both_legacy_manual_text_formats_use_atomic_port_pair(self):
        runtime_path = Path(__file__).resolve().parents[1] / "runtime" / "production_runtime.py"
        source = runtime_path.read_text(encoding="utf-8")
        self.assertEqual(
            source.count("ok_v, ok_i = await _runtime_execution_port().program_voltage_current("),
            2,
        )


if __name__ == "__main__":
    unittest.main()
