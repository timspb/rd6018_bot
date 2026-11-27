import unittest
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from aiogram import Dispatcher

from runtime.production_lifecycle import ProductionRuntimeLifecycle


class ProductionRuntimeLifecycleShutdownTests(unittest.IsolatedAsyncioTestCase):
    async def test_shutdown_hook_cancels_and_joins_owned_workers(self):
        app = SimpleNamespace(
            logger=SimpleNamespace(info=Mock(), warning=Mock()),
            charge_controller=SimpleNamespace(is_active=False),
            hass=SimpleNamespace(close=AsyncMock()),
        )
        lifecycle = ProductionRuntimeLifecycle(app, None)
        worker_cancelled = asyncio.Event()

        async def worker():
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                worker_cancelled.set()
                raise

        task = asyncio.create_task(worker())
        lifecycle._background_tasks = (task,)
        await asyncio.sleep(0)
        with patch("database.close_db", new=AsyncMock()):
            await lifecycle.on_shutdown(None)

        self.assertTrue(worker_cancelled.is_set())
        self.assertTrue(task.done())
        self.assertTrue(task.cancelled())
        self.assertEqual(lifecycle._background_tasks, ())
        app.hass.close.assert_awaited_once()

    async def test_polling_failure_cancels_all_lifecycle_workers_and_closes_connector(self):
        from runtime.production_lifecycle import ProductionRuntimeLifecycle

        started = []
        cancelled = []
        tasks = []
        release = asyncio.Event()

        async def worker(name):
            started.append(name)
            try:
                await release.wait()
            except asyncio.CancelledError:
                cancelled.append(name)
                raise

        live = {
            "battery_voltage": 12.5, "current": 0.0, "ah": 0.0,
            "input_voltage": 0.0, "switch": "off", "is_cv": False, "is_cc": False,
        }
        lock = asyncio.Lock()
        guard = SimpleNamespace(may_run_automatic_control=Mock(return_value=True))
        execution_port = SimpleNamespace(
            _guard_owner_lock=lock,
            session_recovery_guard=guard,
            read_live=AsyncMock(return_value=live),
        )
        controller = SimpleNamespace(
            STAGE_SAFE_WAIT="Safe Wait", current_stage="Idle",
            try_restore_session=Mock(return_value=(False, "")),
        )
        app = SimpleNamespace(
            logger=SimpleNamespace(info=Mock(), warning=Mock(), error=Mock()),
            init_db=AsyncMock(), rotate_if_needed=Mock(),
            trim_log_older_than_days=Mock(return_value=0),
            _load_manual_off_state=Mock(), _load_operator_pause_state=Mock(),
            _safe_float=lambda value, default=0.0: float(value if value is not None else default),
            charge_controller=controller,
            hass=SimpleNamespace(close=AsyncMock()),
            _apply_restore_time_corrections=Mock(), time=SimpleNamespace(time=Mock(return_value=1.0)),
            _restore_allows_auto_enable=Mock(return_value=False), MIN_INPUT_VOLTAGE=10.0,
            _operator_pause_active=Mock(return_value=False),
            dp=SimpleNamespace(include_router=Mock()), router=object(),
            configure_commands=AsyncMock(), run_polling=AsyncMock(),
            data_logger=lambda: worker("data_logger"),
            charge_monitor=lambda: worker("charge_monitor"),
            turn_on=AsyncMock(),
        )
        lifecycle = ProductionRuntimeLifecycle(app, None)

        def start_tasks(*factories):
            names = [
                "periodic_db_cleanup" if factory == lifecycle._periodic_db_cleanup
                else "data_logger" if factory == app.data_logger
                else "charge_monitor" if factory == app.charge_monitor
                else "safety_watchdogs"
                for factory in factories
            ]
            created = tuple(asyncio.create_task(worker(name)) for name in names)
            tasks.extend(created)
            return created

        async def fail_polling(*_args, **_kwargs):
            # Model a polling failure after lifecycle workers are actually
            # scheduled; a never-started task cannot observe CancelledError.
            await asyncio.sleep(0)
            raise RuntimeError("polling failed")

        app.run_polling = fail_polling
        with patch("runtime.production_lifecycle.get_or_create_execution_port", return_value=execution_port), \
             patch("runtime.production_lifecycle.start_background_tasks", side_effect=start_tasks):
            with self.assertRaisesRegex(RuntimeError, "polling failed"):
                await lifecycle.run()

        self.assertCountEqual(started, [
            "periodic_db_cleanup", "data_logger", "charge_monitor", "safety_watchdogs",
        ])
        self.assertEqual(set(cancelled), set(started))
        self.assertTrue(all(task.done() for task in tasks))
        self.assertEqual(lifecycle._background_tasks, ())
        app.hass.close.assert_awaited_once()
        app.turn_on.assert_not_awaited()

    async def test_startup_restore_reads_through_execution_port_safety_owner(self):
        source = Path("runtime/production_lifecycle.py").read_text(encoding="utf-8")
        self.assertIn("live = await execution_port.read_live()", source)
        self.assertNotIn("live = await app.hass.get_all_live()", source)

    async def test_shutdown_hook_receives_aiogram_dispatcher_context(self):
        app = SimpleNamespace(
            logger=SimpleNamespace(info=lambda *args: None, warning=lambda *args: None),
            charge_controller=SimpleNamespace(is_active=False),
            hass=SimpleNamespace(close=AsyncMock()),
        )
        lifecycle = ProductionRuntimeLifecycle(app, telegram_runtime=None)
        dispatcher = Dispatcher()
        dispatcher.shutdown.register(lifecycle.on_shutdown)

        with patch("database.close_db", new=AsyncMock()):
            await dispatcher.shutdown.trigger(dispatcher=dispatcher, router=dispatcher)

        app.hass.close.assert_awaited_once()


    async def test_idle_shutdown_never_waits_for_busy_execution_owner(self):
        lock = asyncio.Lock()
        await lock.acquire()
        app = SimpleNamespace(
            logger=SimpleNamespace(info=Mock(), warning=Mock()),
            charge_controller=SimpleNamespace(is_active=False),
            hass=SimpleNamespace(close=AsyncMock()),
        )
        lifecycle = ProductionRuntimeLifecycle(app, None)
        try:
            with patch("runtime.production_lifecycle.get_or_create_execution_port",
                       side_effect=AssertionError("Idle must not acquire owner")):
                with patch("database.close_db", new=AsyncMock()):
                    await asyncio.wait_for(lifecycle.on_shutdown(None), timeout=0.3)
        finally:
            lock.release()
        app.hass.close.assert_awaited_once()

    async def test_busy_active_owner_skips_unsafe_save_but_closes_clients(self):
        lock = asyncio.Lock()
        await lock.acquire()
        controller = SimpleNamespace(is_active=True, _save_session=Mock())
        app = SimpleNamespace(
            logger=SimpleNamespace(info=Mock(), warning=Mock()),
            charge_controller=controller,
            hass=SimpleNamespace(close=AsyncMock()),
        )
        lifecycle = ProductionRuntimeLifecycle(app, None)
        try:
            with patch("runtime.production_lifecycle.get_or_create_execution_port",
                       return_value=SimpleNamespace(_guard_owner_lock=lock)):
                with patch("runtime.production_lifecycle.SHUTDOWN_SESSION_LOCK_TIMEOUT_S", 0.02):
                    with patch("database.close_db", new=AsyncMock()):
                        await asyncio.wait_for(lifecycle.on_shutdown(None), timeout=0.3)
        finally:
            lock.release()
        controller._save_session.assert_not_called()
        app.hass.close.assert_awaited_once()
        app.logger.warning.assert_called()

    async def test_startup_restore_exception_quarantines_before_monitor_and_blocks_retry(self):
        from application.execution_port import ExecutionPort
        from application.session_recovery_guard import SessionRecoveryGuard
        from runtime.production_lifecycle import ProductionRuntimeLifecycle

        events = []
        guard = SessionRecoveryGuard()

        class Controller:
            STAGE_SAFE_WAIT = "Safe Wait"
            current_stage = "Main Charge"
            is_active = False

            def __init__(self):
                self.restore_calls = 0
                self.partial_restore_applied = False
                self.tick = Mock()

            def try_restore_session(self, *_args, **_kwargs):
                self.restore_calls += 1
                if self.restore_calls == 1:
                    self.current_stage = "Main Charge"
                    self.partial_restore_applied = True
                    events.append(("restore_mutated", guard.quarantined))
                    raise RuntimeError("injected late restore failure")
                return True, "restored"

        controller = Controller()
        live = {"battery_voltage": 12.5, "current": 0.0, "ah": 1.0,
                "input_voltage": 0.0, "switch": "off", "is_cv": False,
                "is_cc": False}
        app = SimpleNamespace(
            logger=SimpleNamespace(info=Mock(), warning=Mock(), error=Mock()),
            session_recovery_guard=guard,
            init_db=AsyncMock(), rotate_if_needed=Mock(),
            trim_log_older_than_days=Mock(return_value=0),
            _load_manual_off_state=Mock(), _load_operator_pause_state=Mock(),
            _safe_float=lambda value, default=0.0: float(value if value is not None else default),
            charge_controller=controller,
            hass=SimpleNamespace(get_all_live=AsyncMock(return_value=live), close=AsyncMock(),
                                 turn_on=AsyncMock()),
            _apply_restore_time_corrections=Mock(),
            time=SimpleNamespace(time=Mock(return_value=1.0)),
            _restore_allows_auto_enable=Mock(return_value=False),
            MIN_INPUT_VOLTAGE=10.0, _operator_pause_active=Mock(return_value=False),
            dp=SimpleNamespace(include_router=Mock()), router=object(),
            configure_commands=AsyncMock(), data_logger=AsyncMock(),
            run_polling=AsyncMock(),
        )
        async def charge_monitor_once():
            self.assertTrue(guard.quarantined)
            events.append(("monitor_callback", guard.quarantined))

        app.charge_monitor = charge_monitor_once
        port = ExecutionPort(app.hass, guard, app=app)
        app.execution_port = port

        def start_tasks(*factories):
            if any(factory == app.charge_monitor for factory in factories):
                events.append(("background_start", guard.quarantined))
                return (asyncio.create_task(app.charge_monitor()),)
            return ()

        polling_calls = 0

        async def polling(*_args, **kwargs):
            nonlocal polling_calls
            polling_calls += 1
            if polling_calls == 1:
                self.assertTrue(guard.quarantined)
                self.assertEqual(guard.state.reason, "startup_restore_failed:RuntimeError")
                await asyncio.sleep(0)
                events.append(("background_ready", guard.quarantined))
                # A later ordinary lifecycle restore attempt is stopped by the
                # same existing startup guard before try_restore_session can run.
                await lifecycle.run()

        app.run_polling = polling
        lifecycle = ProductionRuntimeLifecycle(app, None)
        with patch("runtime.production_lifecycle.start_background_tasks", side_effect=start_tasks):
            await lifecycle.run()

        self.assertEqual(controller.restore_calls, 1)
        self.assertEqual(events[:4], [
            ("restore_mutated", False),
            ("background_start", True),
            ("monitor_callback", True),
            ("background_ready", True),
        ])
        self.assertTrue(guard.quarantined)
        self.assertFalse(guard.may_run_automatic_control())
        self.assertTrue(controller.partial_restore_applied)
        self.assertEqual(app.hass.get_all_live.await_count, 1)
        controller.tick.assert_not_called()
        app.hass.turn_on.assert_not_awaited()

    async def test_successful_startup_restore_still_reaches_background_monitor(self):
        from application.execution_port import ExecutionPort
        from application.session_recovery_guard import SessionRecoveryGuard
        from runtime.production_lifecycle import ProductionRuntimeLifecycle

        events = []
        guard = SessionRecoveryGuard()
        controller = SimpleNamespace(
            STAGE_SAFE_WAIT="Safe Wait", current_stage="Main Charge", is_active=False,
            try_restore_session=Mock(return_value=(True, "restored")),
        )
        live = {"battery_voltage": 12.5, "current": 0.0, "ah": 1.0,
                "input_voltage": 0.0, "switch": "off", "is_cv": False,
                "is_cc": False}
        app = SimpleNamespace(
            logger=SimpleNamespace(info=Mock(), warning=Mock(), error=Mock()),
            session_recovery_guard=guard,
            init_db=AsyncMock(), rotate_if_needed=Mock(),
            trim_log_older_than_days=Mock(return_value=0),
            _load_manual_off_state=Mock(), _load_operator_pause_state=Mock(),
            _safe_float=lambda value, default=0.0: float(value if value is not None else default),
            charge_controller=controller,
            hass=SimpleNamespace(get_all_live=AsyncMock(return_value=live), close=AsyncMock()),
            _apply_restore_time_corrections=Mock(), time=SimpleNamespace(time=Mock(return_value=1.0)),
            _restore_allows_auto_enable=Mock(return_value=True), MIN_INPUT_VOLTAGE=10.0,
            _operator_pause_active=Mock(return_value=False), dp=SimpleNamespace(include_router=Mock()),
            router=object(), configure_commands=AsyncMock(), data_logger=AsyncMock(),
        )

        async def charge_monitor_once():
            self.assertFalse(guard.quarantined)
            events.append(("monitor_callback", guard.quarantined))

        app.charge_monitor = charge_monitor_once
        app.execution_port = ExecutionPort(app.hass, guard, app=app)

        def start_tasks(*factories):
            if any(factory == app.charge_monitor for factory in factories):
                events.append(("background_start", guard.quarantined))
                return (asyncio.create_task(app.charge_monitor()),)
            return ()

        async def polling(*_args, **_kwargs):
            await asyncio.sleep(0)
            events.append(("polling", guard.quarantined))

        app.run_polling = polling
        lifecycle = ProductionRuntimeLifecycle(app, None)
        with patch("runtime.production_lifecycle.start_background_tasks", side_effect=start_tasks):
            await lifecycle.run()

        controller.try_restore_session.assert_called_once()
        self.assertFalse(guard.quarantined)
        self.assertEqual(events, [
            ("background_start", False),
            ("monitor_callback", False),
            ("polling", False),
        ])


if __name__ == "__main__":
    unittest.main()
