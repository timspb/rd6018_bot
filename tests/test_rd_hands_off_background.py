import unittest
from types import SimpleNamespace

from rd_hands_off_background import install_hands_off_background_isolation


class DummyController:
    def __init__(self):
        self.tick_calls = 0
        self.restore_calls = 0
        self.last_update_time = 0.0
        self.notify = None

    async def tick(self, *args, **kwargs):
        self.tick_calls += 1
        return {"turn_off": True, "notify": "legacy tick"}

    def try_restore_session(self, *args, **kwargs):
        self.restore_calls += 1
        return True, "restored"


class HandsOffBackgroundIsolationTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _app(*, hands_off=True, release_in_progress=False):
        controller = DummyController()
        manager = SimpleNamespace(
            hands_off=hands_off,
            release_in_progress=release_in_progress,
        )
        hard_stop_calls = []
        notices = []
        events = []
        cleared = {"manual": 0, "pause": 0}
        state = {"manual": True, "pause": True}

        async def hard_stop(*args, **kwargs):
            hard_stop_calls.append((args, kwargs))

        def manual_off_active():
            return state["manual"]

        def clear_manual():
            state["manual"] = False
            cleared["manual"] += 1

        def pause_active():
            return state["pause"]

        def clear_pause():
            state["pause"] = False
            cleared["pause"] += 1

        def notify(message, *args, **kwargs):
            notices.append(str(message))

        def log_event(*args, **kwargs):
            events.append((args, kwargs))

        app = SimpleNamespace(
            charge_controller=controller,
            _hard_stop_charge=hard_stop,
            _has_manual_off_condition=manual_off_active,
            _clear_manual_off=clear_manual,
            _operator_pause_active=pause_active,
            _clear_operator_pause=clear_pause,
            _charge_notify=notify,
            log_event=log_event,
        )
        controller.notify = notify
        install_hands_off_background_isolation(app, manager)
        return app, manager, controller, hard_stop_calls, notices, events, cleared, state

    async def test_hands_off_tick_is_observational_and_keeps_legacy_watchdog_heartbeat_fresh(self):
        app, _manager, controller, *_ = self._app(hands_off=True)
        before = controller.last_update_time

        actions = await controller.tick(12.0, 1.0, None, False, 0.0)

        self.assertEqual(actions, {})
        self.assertEqual(controller.tick_calls, 0)
        self.assertGreater(controller.last_update_time, before)

    async def test_hands_off_background_restore_probe_is_inert(self):
        _app, _manager, controller, *_ = self._app(hands_off=True)

        result = controller.try_restore_session(12.0, 1.0, 0.0, output_is_on=True)

        self.assertEqual(result, (False, None))
        self.assertEqual(controller.restore_calls, 0)

    async def test_hands_off_hard_stop_helper_does_not_actuate(self):
        app, _manager, _controller, hard_stop_calls, *_ = self._app(hands_off=True)

        await app._hard_stop_charge()

        self.assertEqual(hard_stop_calls, [])

    async def test_hands_off_retires_stale_manual_off_and_operator_pause_authority(self):
        app, _manager, _controller, _hard, _notices, _events, cleared, state = self._app(
            hands_off=True
        )

        self.assertFalse(app._has_manual_off_condition())
        self.assertFalse(app._operator_pause_active())

        self.assertFalse(state["manual"])
        self.assertFalse(state["pause"])
        self.assertEqual(cleared, {"manual": 1, "pause": 1})

    async def test_hands_off_suppresses_only_legacy_control_claim_notifications(self):
        app, _manager, _controller, _hard, notices, *_ = self._app(hands_off=True)

        app._charge_notify("🌡 Температура блока 60°C ≥ 55°C. Выход выключен для защиты БП.")
        app._charge_notify("⚠️ Выход включен, но потребление отсутствует. Не забудьте выключить прибор.")
        app._charge_notify("observer: external Mix evidence updated")

        self.assertEqual(notices, ["observer: external Mix evidence updated"])

    async def test_hands_off_filters_legacy_control_events_but_keeps_observer_events(self):
        app, _manager, _controller, _hard, _notices, events, *_ = self._app(hands_off=True)

        app.log_event("Idle", 0.0, 0.0, 0.0, 0.0, "TEMP_INT_PRECRITICAL_60C")
        app.log_event("Idle", 0.0, 0.0, 0.0, 0.0, "WATCHDOG_TIMEOUT")
        app.log_event("Idle", 0.0, 0.0, 0.0, 0.0, "D063_OBSERVER_SAMPLE")

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0][5], "D063_OBSERVER_SAMPLE")

    async def test_pb_managed_behavior_is_unchanged(self):
        app, _manager, controller, hard_stop_calls, notices, events, cleared, state = self._app(
            hands_off=False
        )

        actions = await controller.tick(12.0, 1.0, 25.0, False, 0.0)
        restored = controller.try_restore_session(12.0, 1.0, 0.0)
        await app._hard_stop_charge()
        self.assertTrue(app._has_manual_off_condition())
        self.assertTrue(app._operator_pause_active())
        app._charge_notify("🌡 Температура блока 60°C ≥ 55°C. Выход выключен для защиты БП.")
        app.log_event("Main", 1.0, 1.0, 25.0, 0.0, "WATCHDOG_TIMEOUT")

        self.assertTrue(actions["turn_off"])
        self.assertEqual(restored, (True, "restored"))
        self.assertEqual(controller.tick_calls, 1)
        self.assertEqual(controller.restore_calls, 1)
        self.assertEqual(len(hard_stop_calls), 1)
        self.assertEqual(len(notices), 1)
        self.assertEqual(len(events), 1)
        self.assertEqual(cleared, {"manual": 0, "pause": 0})
        self.assertTrue(state["manual"])
        self.assertTrue(state["pause"])

    async def test_precommit_live_release_keeps_pb_safety_active(self):
        app, _manager, controller, hard_stop_calls, *_ = self._app(
            hands_off=False,
            release_in_progress=True,
        )

        await controller.tick(12.0, 1.0, 25.0, False, 0.0)
        await app._hard_stop_charge()

        self.assertEqual(controller.tick_calls, 1)
        self.assertEqual(len(hard_stop_calls), 1)


if __name__ == "__main__":
    unittest.main()
