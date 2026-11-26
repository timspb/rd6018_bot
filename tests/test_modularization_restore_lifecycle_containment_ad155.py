"""Late restore failures contained by the production startup recovery owner."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from application.execution_port import get_or_create_execution_port
from application.session_recovery_guard import SessionRecoveryGuard
import charge_controller
from production_controller import create_production_charge_host
from runtime.charge import persistence
from runtime.production_lifecycle import ProductionRuntimeLifecycle
from tests.test_modularization_auto_restore_atomic_admission import _valid_document


class _StopAfterOneCycle(Exception):
    pass


def _failure_case(name):
    """Return a real late restore seam and its minimal triggering document."""
    document = _valid_document(saved_at=50_000.0)
    reached = {"count": 0}
    def fail():
        reached["count"] += 1
        raise RuntimeError(name)
    def inject(host):
        if name == "reset_delta_blanking":
            host._reset_delta_and_blanking = lambda _now: fail()
        elif name == "history_deque_clear":
            class BadDeque:
                maxlen = 8
                def clear(self): fail()
                def extend(self, _values): raise AssertionError("clear should fail first")
            host._stage_history = BadDeque()
            document["stage_history"] = [{"stage": "Main Charge"}]
        elif name == "stage_limit_getter":
            host._get_stage_max_hours = lambda: fail()
        elif name == "target_getter":
            host._get_target_v_i = lambda: fail()
        elif name == "rules_summary":
            host._session_rules_summary = lambda: fail()
        elif name == "target_clearing":
            # Canonical persisted stage plus an expired Mix deadline enters
            # project_restore_stage_timeline(clear_restored_targets=True).
            document.update(stage="Mix Mode", target_finish_time=49_999.0, finish_timer_start=49_900.0)
            host._clear_restored_targets = lambda: fail()
        elif name == "terminal_normalization":
            # A terminal Done document without explicit storage outcome asks
            # the real restore finalizer to normalize the persisted record.
            document.update(stage="Done")
        elif name in ("terminal_save", "terminal_not_committed", "terminal_uncertain"):
            document.update(stage="Mix Mode", target_finish_time=49_999.0, finish_timer_start=49_900.0)
    return document, inject, reached


class RestoreLifecycleContainmentAD155(unittest.IsolatedAsyncioTestCase):
    NOW = 50_000.0

    CASES = (
        "reset_delta_blanking", "history_deque_clear", "stage_limit_getter",
        "target_getter", "rules_summary", "header_logging", "target_clearing",
        "terminal_normalization", "terminal_save", "terminal_not_committed",
        "terminal_uncertain",
    )

    async def _run_startup(self, failure=None, *, cancel_after_restore=False):
        guard = SessionRecoveryGuard()
        events = []
        document, inject, reached = _failure_case(failure) if failure else (_valid_document(saved_at=50_000.0), lambda _host: None, None)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "session.json"
            live = {"battery_voltage": 12.5, "current": 0.0, "ah": 1.0,
                    "input_voltage": 60.5 if cancel_after_restore else 0.0,
                    "switch": "off", "is_cv": False, "is_cc": False}
            owner = SimpleNamespace(get_all_live=AsyncMock(return_value=live), close=AsyncMock(), turn_on=AsyncMock())
            host = create_production_charge_host(owner)
            if cancel_after_restore:
                document.update(
                    stage=host.STAGE_SAFE_WAIT,
                    safe_wait_next_stage=host.STAGE_MAIN,
                    safe_wait_target_v=13.8,
                    safe_wait_target_i=1.0,
                    safe_wait_start=self.NOW - 1,
                )
            inject(host)
            # Some trigger closures update the persisted document as well as
            # installing the host seam; serialize only after both are applied.
            path.write_text(json.dumps(document), encoding="utf-8")
            app = SimpleNamespace(
                logger=SimpleNamespace(info=Mock(), warning=Mock(), error=Mock()),
                session_recovery_guard=guard, init_db=AsyncMock(), rotate_if_needed=Mock(),
                trim_log_older_than_days=Mock(return_value=0), _load_manual_off_state=Mock(),
                _load_operator_pause_state=Mock(), _safe_float=lambda v, default=0.0: float(v if v is not None else default),
                charge_controller=host, hass=owner, _apply_restore_time_corrections=Mock(),
                time=SimpleNamespace(time=Mock(return_value=1.0)),
                _restore_allows_auto_enable=Mock(return_value=cancel_after_restore),
                MIN_INPUT_VOLTAGE=10.0, _operator_pause_active=Mock(return_value=False),
                dp=SimpleNamespace(include_router=Mock()), router=object(), configure_commands=AsyncMock(),
                data_logger=AsyncMock(), run_polling=AsyncMock(),
            )
            if cancel_after_restore:
                def assert_safe_wait_stage(controller):
                    self.assertEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)
                    return True

                app._restore_allows_auto_enable = Mock(
                    side_effect=assert_safe_wait_stage
                )
            app.charge_monitor = AsyncMock()
            def start_tasks(*factories):
                events.append(("background", tuple(factories), guard.quarantined))
                return ()
            async def polling(*_a, **_kw):
                events.append(("polling", guard.quarantined))
            app.run_polling = polling
            execution_port = get_or_create_execution_port(app)
            if cancel_after_restore:
                execution_port.program_voltage = AsyncMock(side_effect=asyncio.CancelledError())
            real_restore = charge_controller.restore_session
            real_finalizer = persistence.finalize_restored_session
            real_save = charge_controller.save_session
            injections = {"normalization": 0, "save": 0}
            finalizer_arguments = []
            def finalizer(*args, **kwargs):
                finalizer_arguments.append(kwargs)
                if failure == "terminal_normalization":
                    injections["normalization"] += 1
                    raise RuntimeError(failure)
                return real_finalizer(*args, **kwargs)
            def save(*args, **kwargs):
                if failure in ("terminal_save", "terminal_not_committed", "terminal_uncertain"):
                    injections["save"] += 1
                    if failure == "terminal_not_committed":
                        from runtime.charge.session_atomic import WriteStatus
                        return WriteStatus.NOT_COMMITTED, path.read_bytes()
                    if failure == "terminal_uncertain":
                        from runtime.charge.session_atomic import WriteStatus
                        return WriteStatus.OUTCOME_UNCERTAIN, None
                    raise RuntimeError(failure)
                return real_save(*args, **kwargs)
            with patch("charge_controller.SESSION_FILE", str(path)), \
                 patch("charge_controller.restore_session", wraps=real_restore) as restore_call, \
                 patch("runtime.production_lifecycle.start_background_tasks", side_effect=start_tasks), \
                 patch("runtime.charge.persistence.time.time", return_value=50_000.0), \
                 patch.object(persistence, "finalize_restored_session", side_effect=finalizer) as finalizer_call, \
                 patch("charge_controller.save_session", side_effect=save) as save_call, \
                 patch.object(persistence, "log_session_header", side_effect=(
                     RuntimeError(failure) if failure == "header_logging" else persistence.log_session_header
                 )) as header_call:
                if cancel_after_restore:
                    with self.assertRaises(asyncio.CancelledError):
                        await ProductionRuntimeLifecycle(app, None).run()
                    app.execution_port.program_voltage.assert_awaited_once_with(13.8)
                    self.assertTrue(guard.quarantined)
                    self.assertEqual(guard.state.reason, "startup_restore_cancelled")
                    self.assertEqual(len(events), 1)
                    self.assertEqual(len(events[0][1]), 1)
                    self.assertEqual(events[0][1][0].__name__, "_periodic_db_cleanup")
                else:
                    await ProductionRuntimeLifecycle(app, None).run()
            restore_call.assert_called_once()
            if failure in self.CASES:
                if failure not in ("terminal_normalization", "terminal_save", "terminal_not_committed",
                                   "terminal_uncertain", "header_logging"):
                    self.assertEqual(reached["count"], 1, f"{failure} injection was not reached exactly once")
                if failure == "terminal_normalization":
                    self.assertEqual(injections["normalization"], 1)
                    finalizer_call.assert_called_once()
                    self.assertTrue(finalizer_arguments[0]["normalize_done_document"])
                elif failure in ("terminal_save", "terminal_not_committed", "terminal_uncertain"):
                    self.assertEqual(injections["save"], 1)
                    save_call.assert_called_once()
                if failure == "header_logging":
                    # The patched persistence lookup is invoked once by restore.
                    self.assertEqual(header_call.call_count, 1)
                if failure == "target_clearing":
                    finalizer_call.assert_not_called()
            return guard, host, events, owner, app

    async def test_every_late_restore_failure_is_quarantined_before_background_start(self):
        for case in self.CASES:
            with self.subTest(boundary=case):
                guard, host, events, owner, app = await self._run_startup(case)
                self.assertTrue(guard.quarantined)
                self.assertEqual(guard.state.reason, "startup_restore_failed:RuntimeError")
                self.assertEqual(len(events), 3)
                self.assertEqual(events[0][0], "background")
                self.assertEqual(events[0][2], False)  # cleanup-only, before restore
                self.assertEqual(len(events[0][1]), 1)
                self.assertEqual(events[0][1][0].__name__, "_periodic_db_cleanup")
                self.assertNotIn(app.data_logger, events[0][1])
                self.assertEqual(events[1][0], "background")
                self.assertIs(events[1][1][0], app.data_logger)
                self.assertIs(events[1][1][1], app.charge_monitor)
                self.assertEqual(len(events[1][1]), 3)
                self.assertEqual(events[1][2], True)
                self.assertEqual(events[2], ("polling", True))
                self.assertFalse(guard.may_run_automatic_control())
                self.assertFalse(host._stage_tracking_enabled)
                owner.turn_on.assert_not_awaited()
                from tests.test_data_logger_recovery_quarantine import DataLoggerRecoveryQuarantineTests
                _loop, data_controller, stage_before, tick, data_owner, _record = (
                    await DataLoggerRecoveryQuarantineTests()._run_one_cycle(
                        quarantined=False, guard=guard,
                    )
                )
                tick.assert_not_awaited()
                self.assertEqual(data_controller.current_stage, stage_before)
                data_owner.safe_enable_output.assert_not_awaited()
                data_owner.turn_on.assert_not_awaited()
                data_owner.set_voltage.assert_not_awaited()
                data_owner.set_current.assert_not_awaited()

    async def test_successful_restore_does_not_quarantine_and_startup_continues(self):
        guard, host, events, _owner, app = await self._run_startup()
        self.assertFalse(guard.quarantined)
        self.assertTrue(host._stage_tracking_enabled)
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0][0:1], ("background",))
        self.assertEqual(len(events[0][1]), 1)
        self.assertEqual(events[0][1][0].__name__, "_periodic_db_cleanup")
        self.assertNotIn(app.data_logger, events[0][1])
        self.assertFalse(events[0][2])
        self.assertEqual(events[1][0], "background")
        self.assertIs(events[1][1][0], app.data_logger)
        self.assertIs(events[1][1][1], app.charge_monitor)
        self.assertFalse(events[1][2])
        self.assertEqual(events[2], ("polling", False))
        from tests.test_data_logger_recovery_quarantine import DataLoggerRecoveryQuarantineTests
        _loop, _controller, _stage, tick, _owner, _record = await DataLoggerRecoveryQuarantineTests()._run_one_cycle(
            quarantined=False, guard=guard,
        )
        tick.assert_awaited_once()

    async def test_cancellation_at_first_post_restore_await_latches_guard_and_reraises(self):
        guard, host, _events, _owner, _app = await self._run_startup(cancel_after_restore=True)
        self.assertTrue(guard.quarantined)
        self.assertEqual(guard.state.reason, "startup_restore_cancelled")
        self.assertFalse(guard.may_run_automatic_control())
        self.assertTrue(host._stage_tracking_enabled)


if __name__ == "__main__":
    unittest.main()
