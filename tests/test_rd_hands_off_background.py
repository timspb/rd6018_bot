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


class BackgroundAuthorityIsolationTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _app(
        *,
        hands_off=False,
        edge_autonomous=False,
        release_in_progress=False,
        startup_ready=True,
        reconciliation_started=True,
        recovery_scope=False,
        with_startup=True,
    ):
        controller = DummyController()
        manager = SimpleNamespace(
            hands_off=hands_off,
            edge_autonomous=edge_autonomous,
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
        if with_startup:
            app.rd_startup_authority_gate = SimpleNamespace(
                managed_actuation_ready=startup_ready,
                reconciliation_started=reconciliation_started,
                recovery_scope=recovery_scope,
            )
        controller.notify = notify
        install_hands_off_background_isolation(app, manager)
        return app, manager, controller, hard_stop_calls, notices, events, cleared, state

    async def test_hands_off_tick_restore_and_hard_stop_are_observational(self):
        app, _manager, controller, hard_stop_calls, *_ = self._app(
            hands_off=True,
            startup_ready=True,
        )
        before = controller.last_update_time

        actions = await controller.tick(12.0, 1.0, None, False, 0.0)
        restored = controller.try_restore_session(12.0, 1.0, 0.0, output_is_on=True)
        await app._hard_stop_charge()

        self.assertEqual(actions, {})
        self.assertEqual(restored, (False, None))
        self.assertEqual(controller.tick_calls, 0)
        self.assertEqual(controller.restore_calls, 0)
        self.assertEqual(hard_stop_calls, [])
        self.assertGreater(controller.last_update_time, before)

    async def test_explicit_autonomous_is_observational_even_without_hands_off_flag(self):
        app, _manager, controller, hard_stop_calls, *_ = self._app(
            hands_off=False,
            edge_autonomous=True,
            startup_ready=True,
        )

        self.assertEqual(await controller.tick(), {})
        self.assertEqual(controller.try_restore_session(), (False, None))
        await app._hard_stop_charge()

        self.assertEqual(controller.tick_calls, 0)
        self.assertEqual(controller.restore_calls, 0)
        self.assertEqual(hard_stop_calls, [])

    async def test_unresolved_started_startup_suspends_without_destroying_policy(self):
        app, _manager, controller, hard_stop_calls, notices, events, cleared, state = self._app(
            startup_ready=False,
            reconciliation_started=True,
            recovery_scope=False,
        )

        self.assertEqual(await controller.tick(), {})
        self.assertEqual(controller.try_restore_session(), (False, None))
        await app._hard_stop_charge()
        self.assertFalse(app._has_manual_off_condition())
        self.assertFalse(app._operator_pause_active())
        app._charge_notify("🚨 Связь потеряна во время активного заряда!")
        app.log_event("Idle", 0.0, 0.0, 0.0, 0.0, "LINK_LOST_DURING_CHARGE")

        self.assertEqual(hard_stop_calls, [])
        self.assertEqual(notices, [])
        self.assertEqual(events, [])
        self.assertEqual(cleared, {"manual": 0, "pause": 0})
        self.assertEqual(state, {"manual": True, "pause": True})

    async def test_installed_but_not_started_gate_does_not_leak_into_helpers(self):
        app, _manager, controller, hard_stop_calls, notices, events, cleared, state = self._app(
            startup_ready=False,
            reconciliation_started=False,
        )

        actions = await controller.tick()
        restored = controller.try_restore_session()
        await app._hard_stop_charge()
        self.assertTrue(app._has_manual_off_condition())
        self.assertTrue(app._operator_pause_active())
        app._charge_notify("observer: import-only helper")
        app.log_event("Idle", 0.0, 0.0, 0.0, 0.0, "WATCHDOG_TIMEOUT")

        self.assertTrue(actions["turn_off"])
        self.assertEqual(restored, (True, "restored"))
        self.assertEqual(controller.tick_calls, 1)
        self.assertEqual(controller.restore_calls, 1)
        self.assertEqual(len(hard_stop_calls), 1)
        self.assertEqual(notices, ["observer: import-only helper"])
        self.assertEqual(len(events), 1)
        self.assertEqual(cleared, {"manual": 0, "pause": 0})
        self.assertEqual(state, {"manual": True, "pause": True})

    async def test_external_authority_retires_stale_pb_manual_off_and_pause(self):
        app, _manager, _controller, _hard, _notices, _events, cleared, state = self._app(
            hands_off=True,
            startup_ready=True,
        )

        self.assertFalse(app._has_manual_off_condition())
        self.assertFalse(app._operator_pause_active())

        self.assertEqual(cleared, {"manual": 1, "pause": 1})
        self.assertEqual(state, {"manual": False, "pause": False})

    async def test_external_or_unresolved_suppresses_only_legacy_control_claims(self):
        app, _manager, _controller, _hard, notices, events, *_ = self._app(
            edge_autonomous=True,
            startup_ready=True,
        )

        app._charge_notify("🌡 Температура блока 60°C ≥ 55°C. Выход выключен для защиты БП.")
        app._charge_notify("observer: external PSU telemetry updated")
        app.log_event("Idle", 0.0, 0.0, 0.0, 0.0, "TEMP_INT_PRECRITICAL_60C")
        app.log_event("Idle", 0.0, 0.0, 0.0, 0.0, "D063_OBSERVER_SAMPLE")

        self.assertEqual(notices, ["observer: external PSU telemetry updated"])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0][5], "D063_OBSERVER_SAMPLE")

    async def test_managed_reconciled_behavior_is_unchanged(self):
        app, _manager, controller, hard_stop_calls, notices, events, cleared, state = self._app(
            startup_ready=True,
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
        self.assertEqual(state, {"manual": True, "pause": True})

    async def test_task_local_startup_recovery_scope_keeps_containment_helpers_available(self):
        app, _manager, controller, hard_stop_calls, *_ = self._app(
            startup_ready=False,
            reconciliation_started=True,
            recovery_scope=True,
        )

        actions = await controller.tick()
        restored = controller.try_restore_session()
        await app._hard_stop_charge()

        self.assertTrue(actions["turn_off"])
        self.assertEqual(restored, (True, "restored"))
        self.assertEqual(controller.tick_calls, 1)
        self.assertEqual(controller.restore_calls, 1)
        self.assertEqual(len(hard_stop_calls), 1)

    async def test_precommit_live_release_keeps_managed_safety_active(self):
        app, _manager, controller, hard_stop_calls, *_ = self._app(
            hands_off=False,
            edge_autonomous=False,
            release_in_progress=True,
            startup_ready=True,
        )

        await controller.tick(12.0, 1.0, 25.0, False, 0.0)
        await app._hard_stop_charge()

        self.assertEqual(controller.tick_calls, 1)
        self.assertEqual(len(hard_stop_calls), 1)


if __name__ == "__main__":
    unittest.main()
