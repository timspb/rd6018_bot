import asyncio
import types
import unittest

import bot
from rd_startup_authority import RdStartupAuthorityGate


class _FakeController:
    STAGE_MAIN = "Main Charge"
    STAGE_SAFE_WAIT = "Безопасное ожидание"
    STAGE_DONE = "Done"
    STAGE_COOLING = "🌡 Остывание"

    def __init__(self, restored_event):
        self.is_active = False
        self.current_stage = "Idle"
        self.restore_calls = []
        self.start_calls = []
        self._restored_event = restored_event

    def start(self, *args, **kwargs):
        self.start_calls.append((args, kwargs))
        self.is_active = True

    def try_restore_session(self, *args, **kwargs):
        self.restore_calls.append((args, kwargs))
        self.current_stage = self.STAGE_MAIN
        self.is_active = True
        self._restored_event.set()
        return True, "restored"

    def _get_target_v_i(self, _temp_ext):
        return 14.8, 2.0


class _FakeHass:
    def __init__(self):
        self.get_all_calls = 0
        self.turn_on_calls = 0
        self.turn_off_calls = 0
        self.write_calls = 0
        self.live = {
            "autonomous_mode": "off",
            "switch": "off",
            "battery_voltage": 12.5,
            "current": 0.0,
            "ah": 4.2,
            "temp_ext": 25.0,
            "is_cv": "off",
            "is_cc": "off",
        }

    async def get_all_live(self):
        self.get_all_calls += 1
        return dict(self.live)

    async def turn_on(self, entity_id=None):
        self.turn_on_calls += 1
        self.live["switch"] = "on"
        return True

    async def turn_off(self, entity_id=None):
        self.turn_off_calls += 1
        self.live["switch"] = "off"
        return True

    async def set_voltage(self, value):
        self.write_calls += 1
        return True

    async def set_current(self, value):
        self.write_calls += 1
        return True

    async def set_ovp(self, value):
        self.write_calls += 1
        return True

    async def set_ocp(self, value):
        self.write_calls += 1
        return True


class _BlockingGuard:
    def __init__(self, hass, allow_read):
        self.hass = hass
        self.allow_read = allow_read
        self.raw_calls = 0

    async def _raw_live(self):
        self.raw_calls += 1
        await self.allow_read.wait()
        return dict(self.hass.live)


class _FakeManager:
    def __init__(self, guard):
        self.guard = guard
        self.pb_managed = True
        self.hands_off = False
        self._edge_autonomous = False

    @property
    def edge_autonomous(self):
        return self._edge_autonomous

    def _observe_edge_mode(self, live):
        raw = str(live.get("autonomous_mode", "")).strip().lower()
        if raw == "on":
            self._edge_autonomous = True
        elif raw == "off":
            self._edge_autonomous = False

    async def return_pb_control(self):
        self.pb_managed = True
        self.hands_off = False
        return True


class _FakePhysicalControl:
    def __init__(self):
        self.starts = 0
        self.stops = 0

    async def start(self):
        self.starts += 1

    async def stop(self):
        self.stops += 1


class V2StartupAuthorityIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_entrypoint_replays_legacy_restore_race_once_after_managed_recovery(self):
        """Exercise the actual bot.py main orchestration, not only a source contract."""
        shim = bot.main.__globals__
        restored = asyncio.Event()
        allow_edge_read = asyncio.Event()
        hass = _FakeHass()
        controller = _FakeController(restored)
        guard = _BlockingGuard(hass, allow_edge_read)
        manager = _FakeManager(guard)

        async def apply_phase_protection(uv, ui):
            await hass.set_ovp(float(uv) + 0.1)
            await hass.set_ocp(float(ui) + 0.1)

        fake_legacy = types.SimpleNamespace(
            hass=hass,
            charge_controller=controller,
            _safe_float=lambda value, default=0.0: float(value if value is not None else default),
            _apply_restore_time_corrections=lambda _controller, _live: None,
            _restore_allows_auto_enable=lambda ctrl: ctrl.current_stage not in {ctrl.STAGE_DONE, ctrl.STAGE_COOLING},
            _operator_pause_active=lambda: False,
            _apply_phase_protection=apply_phase_protection,
            _cap_current=lambda value: float(value),
            ENTITY_MAP={"switch": "switch.output"},
            last_checkpoint_time=0.0,
            time=types.SimpleNamespace(time=lambda: 1234.0),
            logger=types.SimpleNamespace(info=lambda *args, **kwargs: None),
        )
        gate = RdStartupAuthorityGate(fake_legacy, manager)
        physical = _FakePhysicalControl()
        recovery_calls = 0

        async def init_storage():
            return None

        async def recover():
            nonlocal recovery_calls
            recovery_calls += 1
            return True

        async def legacy_main():
            # Reproduce the production race: legacy startup reaches restore while the
            # authority task is still blocked on the first edge-mode read.
            ok, message = controller.try_restore_session(
                12.4,
                0.0,
                4.1,
                output_is_on=False,
                is_cv=False,
                is_cc=False,
            )
            self.assertFalse(ok)
            self.assertIsNone(message)
            self.assertTrue(gate.deferred_restore_requested)
            self.assertEqual(controller.restore_calls, [])

            allow_edge_read.set()
            await asyncio.wait_for(restored.wait(), timeout=1.0)
            for _ in range(20):
                if not gate.deferred_restore_requested:
                    break
                await asyncio.sleep(0)
            self.assertFalse(gate.deferred_restore_requested)

        replacements = {
            "_legacy": fake_legacy,
            "_legacy_main": legacy_main,
            "_rd_startup_authority": gate,
            "_recover_managed_startup_authority": recover,
            "_physical_test_control": physical,
            "init_v2_storage": init_storage,
        }
        originals = {name: shim[name] for name in replacements}
        try:
            shim.update(replacements)
            await bot.main()
        finally:
            shim.update(originals)

        self.assertEqual(recovery_calls, 1)
        self.assertEqual(len(controller.restore_calls), 1)
        args, kwargs = controller.restore_calls[0]
        self.assertEqual(args, (12.5, 0.0, 4.2))
        self.assertEqual(kwargs["output_is_on"], False)
        self.assertTrue(gate.managed_actuation_ready)
        self.assertEqual(hass.get_all_calls, 1)
        self.assertEqual(hass.turn_on_calls, 1)
        self.assertEqual(hass.turn_off_calls, 0)
        self.assertEqual(hass.write_calls, 4)
        self.assertEqual(hass.live["switch"], "on")
        self.assertEqual(fake_legacy.last_checkpoint_time, 1234.0)
        self.assertEqual(physical.starts, 1)
        self.assertEqual(physical.stops, 1)


if __name__ == "__main__":
    unittest.main()
