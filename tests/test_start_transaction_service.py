import asyncio
import json
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from aiogram.enums import ParseMode

from pb_domain import BatteryCondition, ChargeIntent
from runtime.safety.output_policy import EnableResult, SafetyViolation
from application.start_transaction_service import (
    native_off_timestamp_after_receipt, retire_previous_guard_for_start,
    start_off_receipt_completed_at, start_profile_transactional, start_profile_transactional_result,
)
from charge_controller import ManagedChargeController
from application.session_recovery_guard import SessionRecoveryGuard
from application.guard_execution_owner_lock import GuardExecutionOwnerLock
from runtime.output.command_receipt import OutputCommandReceipt
from runtime.charge.persistence import (
    StartPendingAction, StartPendingResult, StartPendingStatus,
    begin_start_pending as begin_start_pending_real,
    finish_start_pending as finish_start_pending_real,
    read_start_pending as read_start_pending_real,
    project_session_document as project_session_document_real,
)
from runtime.charge.session import TraceIdentitySnapshot


class FakeMessage:
    def __init__(self):
        self.chat = types.SimpleNamespace(id=123)
        self.from_user = types.SimpleNamespace(id=7)
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))


class FakeController(ManagedChargeController):
    STAGE_PREP = "Подготовка"
    STAGE_MAIN = "Main Charge"

    def __init__(
        self, hass, notify_cb=None, *, host_configuration=None,
        battery_id=None, recovery_intent=ChargeIntent.RECOVERY,
        condition_before=BatteryCondition.UNKNOWN,
    ):
        super().__init__(
            hass, notify_cb, host_configuration=host_configuration,
            battery_id=battery_id, recovery_intent=recovery_intent,
            condition_before=condition_before,
        )
        self.started = False
        self.start_calls = 0
        self.stopped = False
        self.context = None
        self.reset_blanking_at = None
        self.clear_calls = 0
        self.trace_identity = None
        self.start_timestamp = None

    def configure_recovery_context(self, **kwargs):
        super().configure_recovery_context(**kwargs)
        self.context = kwargs

    def start(self, profile, capacity, **kwargs):
        self.started = True
        self.start_calls += 1
        self.trace_identity = kwargs.get("trace_identity")
        self.start_timestamp = kwargs.get("now_s")
        app = getattr(self.hass, "fake_app", None)
        if app is not None and hasattr(app, "session_path"):
            pending_raw, pending_doc, error = read_start_pending_real(app.session_path)
            app.events.append(("controller_start", pending_raw, pending_doc, error,
                               self, self.trace_identity, self.start_timestamp))
        super().start(profile, capacity, **kwargs)

    def _prep_target(self, temp):
        return 12.0, 0.7

    def _main_target(self, temp):
        return 14.8, 7.0

    def _reset_delta_and_blanking(self, now):
        self.reset_blanking_at = now

    def _clear_session_file(self):
        self.clear_calls += 1

    def stop(self, clear_session=True):
        self.stopped = True
        super().stop(clear_session=clear_session)


class FakeHass:
    def __init__(self, result):
        self.result = result
        self.enable_kwargs = None
        self.live_read_calls = 0
        self.live = {
            "battery_voltage": 12.6,
            "current": 0.0,
            "temp_ext": 25.0,
            "temp_int": 32.0,
            "input_voltage": 64.0,
            "switch": "off",
            "ovp_triggered": "off",
            "ocp_triggered": "off",
            "set_voltage": 14.8,
            "set_current": 7.0,
            "ovp": 14.9,
            "ocp": 7.1,
            "ah": 0.0,
        }
        self.report_value = 0
        self.report_generation = 7
        self.report_timestamp_override = None
        self.report_sequence = None
        self.native_report_calls = 0
        self.last_native_report = None

    async def get_all_live(self):
        self.live_read_calls += 1
        return dict(self.live)

    async def get_native_physical_output_report(self):
        self.native_report_calls += 1
        if self.report_sequence:
            report = self.report_sequence.pop(0)
            return report() if callable(report) else report
        timestamp = (time.monotonic() if self.report_timestamp_override is None
                    else self.report_timestamp_override)
        self.last_native_report = (self.report_value, {
            "status": "ok",
            "native_type": "SensorState",
            "connection_generation": self.report_generation,
            "subscription_timestamp_monotonic": timestamp,
        })
        return self.last_native_report


class FakePort:
    def __init__(self, hass, result):
        self.hass = hass
        self.result = result
        self.session_recovery_guard = SessionRecoveryGuard()
        self._guard_owner_lock = asyncio.Lock()
        self.off_calls = 0
        self.receipt_enabled = True
        self.enable_pending_seen = False
        self.enable_started = asyncio.Event()
        self.enable_gate = None
        self.off_started = asyncio.Event()
        self.off_gate = None
        self.receipt_override = None
        self.trace = []
        self.live_owner = None
        self.live_read_calls = 0

    def authorize_managed_start(self):
        return True

    async def read_live(self):
        self.live_read_calls += 1
        owner = self.live_owner or self.hass
        return await owner.get_all_live()

    async def enable(self, intent, *, identity=None, recipe_voltage_ceiling_v=None):
        app = self.hass.fake_app
        if hasattr(app, "session_path"):
            raw, envelope, error = read_start_pending_real(app.session_path)
            self.trace.append(("enable", raw, envelope, error, identity))
            app.events.append(("enable", raw, envelope, error, identity))
        self.enable_started.set()
        if self.enable_gate is not None:
            await self.enable_gate.wait()
        self.hass.enable_kwargs = {
            "voltage_v": intent.requested_voltage_v,
            "current_a": intent.requested_current_a,
            "recipe_voltage_ceiling_v": recipe_voltage_ceiling_v,
        }
        return types.SimpleNamespace(
            verified=bool(self.result.enabled),
            reason=self.result.detail,
            detail=self.result.detail,
        )

    async def request_emergency_off_receipt(self):
        self.off_calls += 1
        self.off_started.set()
        if self.off_gate is not None:
            await self.off_gate.wait()
        if not self.receipt_enabled:
            return None
        if self.receipt_override is not None:
            return self.receipt_override
        return OutputCommandReceipt(
            request_id=f"test-off-{self.off_calls}",
            requested_target=False,
            terminal_status="APPLIED",
            observed_r18=0,
            terminal_completed_monotonic=time.monotonic() - 0.001,
            connection_generation=7,
            raw_terminal_identity="test-terminal-off",
        )


class FakeApp:
    ParseMode = ParseMode
    OVP_OFFSET = 0.1
    OCP_OFFSET = 0.1
    ENTITY_MAP = {"switch": "switch.rd6018"}

    def __init__(self, result):
        self.hass = FakeHass(result)
        self.charge_controller = FakeController(self.hass)
        self.execution_port = FakePort(self.hass, result)
        self.hass.fake_app = self
        self.user_dashboard = {}
        self.last_checkpoint_time = 0.0
        self.last_chat_id = None
        self.last_user_id = None
        self.time = types.SimpleNamespace(time=lambda: 1000.0)
        self.events = []
        self.pause_active = False

    @staticmethod
    def _safe_float(value, default=0.0):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _cap_current(value):
        return min(12.0, max(0.1, float(value)))

    def log_event(self, *args):
        self.events.append(args)

    def _operator_pause_active(self):
        return self.pause_active

    def _clear_operator_pause(self):
        self.pause_active = False

    async def send_dashboard(self, *args, **kwargs):
        return 1


PENDING = types.SimpleNamespace(
    profile="EFB",
    capacity_ah=70.0,
    intent=ChargeIntent.RECOVERY,
    battery_id="efb-70",
    condition=BatteryCondition.UNKNOWN,
)


class OffReceiptBoundaryTests(unittest.TestCase):
    def receipt(self, **updates):
        values = dict(
            request_id="off-request", requested_target=False,
            terminal_status="APPLIED", observed_r18=0,
            terminal_completed_monotonic=20.0, connection_generation=7,
            raw_terminal_identity='{"request_id":"off-request"}',
        )
        values.update(updates)
        return OutputCommandReceipt(**values)

    def test_receipt_requires_string_identity_and_real_finite_monotonic_number(self):
        good = self.receipt()
        self.assertEqual(start_off_receipt_completed_at(
            good, receipt_type=OutputCommandReceipt), 20.0)
        for invalid in (
            self.receipt(request_id=1),
            self.receipt(request_id=""),
            self.receipt(terminal_completed_monotonic=True),
            self.receipt(terminal_completed_monotonic="20.0"),
            self.receipt(terminal_completed_monotonic=10 ** 10000),
            self.receipt(terminal_completed_monotonic=float("nan")),
            self.receipt(terminal_completed_monotonic=float("inf")),
        ):
            self.assertIsNone(start_off_receipt_completed_at(
                invalid, receipt_type=OutputCommandReceipt))

    def test_native_off_requires_exact_integer_zero_later_same_generation(self):
        good_meta = {
            "native_type": "SensorState", "status": "ok",
            "connection_generation": 7,
            "subscription_timestamp_monotonic": 20.1,
        }
        self.assertEqual(native_off_timestamp_after_receipt(
            (0, good_meta), receipt_completed_monotonic=20.0,
            connection_generation=7), 20.1)
        invalid_reports = (
            (False, good_meta),
            (0, dict(good_meta, connection_generation=True)),
            (0, dict(good_meta, connection_generation=8)),
            (0, dict(good_meta, subscription_timestamp_monotonic=True)),
            (0, dict(good_meta, subscription_timestamp_monotonic=float("nan"))),
            (0, dict(good_meta, subscription_timestamp_monotonic=20.0)),
        )
        for report in invalid_reports:
            self.assertIsNone(native_off_timestamp_after_receipt(
                report, receipt_completed_monotonic=20.0,
                connection_generation=7))


class V2StartupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._temporary = tempfile.TemporaryDirectory(prefix="rd6018-start-test-")
        self.session_path = Path(self._temporary.name) / "charge_session.json"
        # Expose the isolated canonical path to fake ordering hooks.
        self._session_patch = patch("runtime.charge.persistence.SESSION_FILE", str(self.session_path))
        self._session_patch.start()
        self._port_patch = patch(
            "application.start_transaction_service.get_or_create_execution_port",
            side_effect=lambda app: app.execution_port,
        )
        self._port_patch.start()
        self.addCleanup(self._port_patch.stop)
        self.addCleanup(self._session_patch.stop)
        self.addCleanup(self._temporary.cleanup)
    async def test_guarded_restore_candidate_blocks_fresh_start_before_live_read(self):
        app = FakeApp(EnableResult(enabled=True))
        app.charge_controller._guarded_restore_candidate = object()
        message = FakeMessage()

        outcome = await start_profile_transactional_result(app, message, PENDING)

        self.assertFalse(outcome.started)
        self.assertEqual(outcome.persistence_status.value, "NOT_ATTEMPTED")
        self.assertFalse(app.charge_controller.started)
        self.assertIsNone(app.hass.enable_kwargs)
        self.assertEqual(app.hass.live_read_calls, 0)
        self.assertIn("сохранённая MAIN Guard сессия остаётся в карантине",
                      message.answers[-1][0])

    async def test_concurrent_start_waits_for_first_commit_then_rejects_active(self):
        app = FakeApp(EnableResult(enabled=True))
        app.session_path = self.session_path
        # Match the production app-scoped lock type used by ExecutionPort.
        app.execution_port._guard_owner_lock = GuardExecutionOwnerLock()
        app.execution_port.enable_gate = asyncio.Event()
        first = asyncio.create_task(start_profile_transactional(app, FakeMessage(), PENDING))
        await asyncio.wait_for(app.execution_port.enable_started.wait(), timeout=1)
        pending_bytes = self.session_path.read_bytes()
        starts_before_second = app.charge_controller.start_calls
        second_message = FakeMessage()
        second = asyncio.create_task(start_profile_transactional(app, second_message, PENDING))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.assertFalse(second.done())
        self.assertEqual(self.session_path.read_bytes(), pending_bytes)
        self.assertEqual(app.charge_controller.start_calls, starts_before_second)
        self.assertEqual(len(app.execution_port.trace), 1)
        self.assertIs(app.execution_port._guard_owner_lock.owner_task, first)

        # A concrete existing ExecutionPort bound to the same app lock must
        # let its emergency OFF route complete while START owns normal work.
        from application.execution_port import ExecutionPort
        emergency_calls = []

        class EmergencyOwner:
            async def turn_off(self):
                emergency_calls.append("OFF")
                return True

        emergency_port = ExecutionPort(EmergencyOwner())
        emergency_port.bind_guard_owner_lock(app.execution_port._guard_owner_lock)
        self.assertTrue(await asyncio.wait_for(
            emergency_port.request_emergency_off(), timeout=1,
        ))
        self.assertEqual(emergency_calls, ["OFF"])
        self.assertFalse(second.done())

        app.execution_port.enable_gate.set()
        self.assertTrue(await asyncio.wait_for(first, timeout=2))
        self.assertFalse(await asyncio.wait_for(second, timeout=2))
        self.assertEqual(len(app.execution_port.trace), 1)
        self.assertEqual(app.charge_controller.start_calls, starts_before_second)
        self.assertIn("Сначала остановите текущую программу", second_message.answers[-1][0])
        self.assertFalse(app.execution_port._guard_owner_lock.locked())

    async def test_concurrent_start_after_first_quarantine_cannot_bypass_it(self):
        app = FakeApp(EnableResult(enabled=False))
        app.session_path = self.session_path
        app.execution_port._guard_owner_lock = GuardExecutionOwnerLock()
        app.execution_port.enable_gate = asyncio.Event()
        app.execution_port.receipt_override = object()  # malformed evidence forces quarantine
        first = asyncio.create_task(start_profile_transactional(app, FakeMessage(), PENDING))
        await asyncio.wait_for(app.execution_port.enable_started.wait(), timeout=1)
        pending_bytes = self.session_path.read_bytes()
        second_message = FakeMessage()
        second = asyncio.create_task(start_profile_transactional(app, second_message, PENDING))
        await asyncio.sleep(0)
        self.assertFalse(second.done())
        self.assertEqual(self.session_path.read_bytes(), pending_bytes)
        self.assertEqual(len(app.execution_port.trace), 1)

        app.execution_port.enable_gate.set()
        self.assertFalse(await asyncio.wait_for(first, timeout=2))
        self.assertTrue(app.execution_port.session_recovery_guard.quarantined)
        quarantined_bytes = self.session_path.read_bytes()
        self.assertFalse(await asyncio.wait_for(second, timeout=2))
        self.assertEqual(self.session_path.read_bytes(), quarantined_bytes)
        self.assertEqual(len(app.execution_port.trace), 1)
        self.assertEqual(app.charge_controller.start_calls, 1)
        self.assertTrue(second_message.answers[-1][0])

    async def test_concurrent_start_after_cancelled_first_quarantines_cannot_bypass(self):
        app = FakeApp(EnableResult(enabled=True))
        app.session_path = self.session_path
        app.execution_port._guard_owner_lock = GuardExecutionOwnerLock()
        app.execution_port.enable_gate = asyncio.Event()
        app.execution_port.receipt_override = object()
        first = asyncio.create_task(start_profile_transactional(app, FakeMessage(), PENDING))
        await asyncio.wait_for(app.execution_port.enable_started.wait(), timeout=1)
        pending_bytes = self.session_path.read_bytes()
        second_message = FakeMessage()
        second = asyncio.create_task(start_profile_transactional(app, second_message, PENDING))
        await asyncio.sleep(0)
        self.assertFalse(second.done())
        self.assertEqual(self.session_path.read_bytes(), pending_bytes)
        self.assertEqual(len(app.execution_port.trace), 1)

        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(first, timeout=2)
        self.assertTrue(app.execution_port.session_recovery_guard.quarantined)
        quarantined_bytes = self.session_path.read_bytes()
        self.assertFalse(await asyncio.wait_for(second, timeout=2))
        self.assertEqual(self.session_path.read_bytes(), quarantined_bytes)
        self.assertEqual(len(app.execution_port.trace), 1)
        self.assertEqual(app.execution_port.off_calls, 1)
        self.assertEqual(app.charge_controller.start_calls, 1)
        self.assertTrue(second_message.answers[-1][0])

    async def test_start_transaction_reads_initial_output_through_execution_port_safety_owner(self):
        app = FakeApp(EnableResult(enabled=True))
        safety_owner = types.SimpleNamespace(
            get_all_live=AsyncMock(return_value=dict(app.hass.live))
        )
        app.execution_port.live_owner = safety_owner
        app.hass.get_all_live = AsyncMock(
            side_effect=AssertionError("START transaction must not bypass ManagedRuntimeSafetyGuard")
        )

        ok = await start_profile_transactional(app, FakeMessage(), PENDING)

        self.assertTrue(ok)
        safety_owner.get_all_live.assert_awaited_once()
        app.hass.get_all_live.assert_not_awaited()
        self.assertEqual(app.execution_port.live_read_calls, 1)

    async def test_initial_voltage_at_or_above_12_starts_main_atomically(self):
        app = FakeApp(EnableResult(enabled=True))
        message = FakeMessage()
        ok = await start_profile_transactional(app, message, PENDING)
        self.assertTrue(ok)
        self.assertEqual(app.charge_controller.current_stage, app.charge_controller.STAGE_MAIN)
        self.assertEqual(app.charge_controller._stage_history[-1]["ts"], 1000.0)
        self.assertAlmostEqual(app.hass.enable_kwargs["voltage_v"], 14.8)
        self.assertAlmostEqual(app.hass.enable_kwargs["current_a"], 7.0)
        self.assertIn("PREP_SKIPPED_INITIAL_VOLTAGE", app.events[-1][-1])
        self.assertIn("PREP пропущен", message.answers[-1][0])
        committed = json.loads(self.session_path.read_text(encoding="utf-8"))
        self.assertNotIn("start_transaction_pending_v1", committed)
        self.assertGreater(committed["start_transaction_generation"], 0)

    async def test_initial_voltage_below_12_keeps_prep_small_current(self):
        app = FakeApp(EnableResult(enabled=True))
        app.hass.live["battery_voltage"] = 11.99
        message = FakeMessage()
        ok = await start_profile_transactional(app, message, PENDING)
        self.assertTrue(ok)
        self.assertEqual(app.charge_controller.current_stage, app.charge_controller.STAGE_PREP)
        self.assertAlmostEqual(app.hass.enable_kwargs["voltage_v"], 12.0)
        self.assertAlmostEqual(app.hass.enable_kwargs["current_a"], 0.7)
        self.assertIn("PREP_REQUIRED", app.events[-1][-1])

    async def test_success_uses_recipe_aware_safe_enable(self):
        app = FakeApp(EnableResult(enabled=True))
        message = FakeMessage()
        ok = await start_profile_transactional(app, message, PENDING)
        self.assertTrue(ok)
        self.assertTrue(app.charge_controller.started)
        self.assertFalse(app.charge_controller.stopped)
        self.assertAlmostEqual(app.hass.enable_kwargs["recipe_voltage_ceiling_v"], 16.5)
        self.assertIn("Заряд запущен", message.answers[-1][0])

    async def test_pending_commit_precedes_live_start_and_enable_with_detached_parity(self):
        app = FakeApp(EnableResult(enabled=True))
        app.session_path = self.session_path
        live = app.charge_controller
        before = self.session_path.read_bytes() if self.session_path.exists() else None
        real_projection = project_session_document_real
        projections = []
        pending_commits = []

        def observe_projection(controller, *args, **kwargs):
            raw_before = self.session_path.read_bytes() if self.session_path.exists() else None
            document = real_projection(controller, *args, **kwargs)
            raw_after = self.session_path.read_bytes() if self.session_path.exists() else None
            projections.append((controller, raw_before, raw_after, document))
            return document

        def observe_pending_commit(*args, **kwargs):
            result = begin_start_pending_real(*args, **kwargs)
            pending_commits.append(result)
            return result

        with patch("runtime.charge.persistence.project_session_document",
                   side_effect=observe_projection), patch(
                       "runtime.charge.persistence.begin_start_pending",
                       side_effect=observe_pending_commit):
            ok = await start_profile_transactional(app, FakeMessage(), PENDING)

        self.assertTrue(ok)
        self.assertEqual(len(pending_commits), 1)
        self.assertEqual(pending_commits[0].status, StartPendingStatus.COMMITTED)
        starts = [entry for entry in app.events if entry[0] == "controller_start"]
        self.assertEqual(len(starts), 2)
        candidate_start, live_start = starts
        self.assertIsNot(candidate_start[4], live)
        self.assertIs(live_start[4], live)
        self.assertIsNone(candidate_start[1])
        self.assertIsNotNone(live_start[1])
        self.assertIn(b"start_transaction_pending_v1", live_start[1])
        self.assertLess(app.events.index(candidate_start), app.events.index(live_start))
        _, raw_at_start, envelope_at_start, error_at_start, started_controller, identity, start_ts = live_start
        self.assertIs(started_controller, live)
        self.assertIsNone(error_at_start)
        self.assertIsNotNone(raw_at_start)
        self.assertEqual(raw_at_start, pending_commits[0].pending_raw)
        self.assertIn(b"start_transaction_pending_v1", raw_at_start)
        self.assertEqual(envelope_at_start["transaction_id"], json.loads(raw_at_start)["start_transaction_pending_v1"]["transaction_id"])
        self.assertEqual(len(app.execution_port.trace), 1)
        _, raw_at_enable, envelope_at_enable, error_at_enable, enable_identity = app.execution_port.trace[0]
        self.assertIsNone(error_at_enable)
        self.assertEqual(raw_at_enable, raw_at_start)
        self.assertEqual(envelope_at_enable, envelope_at_start)
        self.assertLess(app.events.index(live_start), next(
            index for index, item in enumerate(app.events) if item[0] == "enable"
        ))
        self.assertEqual(len(projections), 2)
        candidate_projection, live_projection = projections
        candidate = candidate_projection[0]
        self.assertIsNot(candidate, live)
        self.assertIs(type(candidate), type(live))
        self.assertEqual(candidate.host_configuration, live.host_configuration)
        self.assertIsNot(candidate._stage_history, live._stage_history)
        self.assertIsNot(candidate._main_sample_evidence, live._main_sample_evidence)
        self.assertIsNone(before)
        self.assertEqual(candidate_projection[1], candidate_projection[2])
        self.assertEqual(live_projection[1], live_projection[2])
        self.assertEqual(candidate_projection[3], live_projection[3])
        self.assertIsInstance(identity, TraceIdentitySnapshot)
        self.assertIs(candidate_start[5], live_start[5])
        self.assertEqual(identity.session_id, enable_identity.session_id)
        self.assertEqual(enable_identity.session_id, identity.session_id)
        self.assertEqual(enable_identity.trace_id, f"auto_start:{identity.session_id}")
        self.assertEqual(start_ts, 1000.0)
        self.assertEqual(candidate_start[6], live_start[6])
        self.assertEqual(live.start_timestamp, start_ts)
        self.assertIs(live.trace_identity, identity)
        self.assertIs(app.charge_controller, live)

    async def test_start_retires_guard_from_embedded_retired_prior_after_pending_write(self):
        app = FakeApp(EnableResult(enabled=True))
        app.session_path = self.session_path
        guard_identity = types.SimpleNamespace(session_id="old-session", battery_id="old-battery")
        app.charge_controller._main_current_guard = guard_identity
        app.charge_controller._main_current_guard_revision = 4
        prior = {
            "owner": "runtime.charge.persistence",
            "schema_version": 1,
            "state": "retired",
            "stage": "RETIRED",
            "retirement_kind": "operator_recovery_clearance",
            "output_intent": "verified_off",
            "verified_off_transaction_id": "old-off-transaction",
            "session_id": "old-session",
            "battery_id": "old-battery",
            "start_transaction_generation": 0,
        }
        prior_raw = json.dumps(prior, ensure_ascii=False, indent=2).encode("utf-8")
        self.session_path.write_bytes(prior_raw)
        real_retire = retire_previous_guard_for_start
        real_projection = project_session_document_real
        retirement_calls = []
        projections = []

        def observe_projection(controller, *args, **kwargs):
            document = real_projection(controller, *args, **kwargs)
            projections.append((controller, document))
            return document

        def observe_retirement(controller, *, session_file, **kwargs):
            pending_raw, pending_doc, error = read_start_pending_real(self.session_path)
            self.assertIsNotNone(pending_raw)
            self.assertIsNotNone(pending_doc)
            self.assertIsNone(error)
            self.assertEqual(Path(session_file).read_bytes(), prior_raw)
            retirement_calls.append((controller, pending_raw))
            return real_retire(controller, session_file=session_file, **kwargs)

        with patch("runtime.charge.persistence.project_session_document",
                   side_effect=observe_projection), patch(
                       "application.start_transaction_service.retire_previous_guard_for_start",
                       side_effect=observe_retirement):
            ok = await start_profile_transactional(app, FakeMessage(), PENDING)

        self.assertTrue(ok)
        self.assertEqual(len(retirement_calls), 1)
        self.assertEqual(len(projections), 2)
        self.assertIsNot(projections[0][0], projections[1][0])
        self.assertEqual(projections[0][1], projections[1][1])
        self.assertIs(retirement_calls[0][0], app.charge_controller)
        self.assertIsNone(app.charge_controller._main_current_guard)
        self.assertIsNone(app.charge_controller._main_current_guard_revision)
        self.assertEqual(app.execution_port.off_calls, 0)
        committed = json.loads(self.session_path.read_bytes().decode("utf-8"))
        self.assertNotIn("main_current_guard_v1", committed)

    async def test_unproven_embedded_prior_guard_fails_closed_and_restores_exact_bytes(self):
        cases = (
            ("active", "old-session", "old-battery"),
            ("retired", "different-session", "different-battery"),
        )
        for state, session_id, battery_id in cases:
            with self.subTest(state=state, session_id=session_id):
                app = FakeApp(EnableResult(enabled=True))
                app.session_path = self.session_path
                app.charge_controller._main_current_guard = types.SimpleNamespace(
                    session_id="old-session", battery_id="old-battery",
                )
                prior = {
                    "owner": "runtime.charge.persistence",
                    "schema_version": 1,
                    "state": state,
                    "stage": "RETIRED" if state == "retired" else "Main Charge",
                    "retirement_kind": "operator_recovery_clearance",
                    "output_intent": "verified_off",
                    "verified_off_transaction_id": "old-off-transaction",
                    "session_id": session_id,
                    "battery_id": battery_id,
                    "start_transaction_generation": 0,
                }
                prior_raw = json.dumps(prior, ensure_ascii=False, indent=2).encode("utf-8")
                self.session_path.write_bytes(prior_raw)

                ok = await start_profile_transactional(app, FakeMessage(), PENDING)

                self.assertFalse(ok)
                self.assertEqual(self.session_path.read_bytes(), prior_raw)
                self.assertEqual(app.execution_port.off_calls, 0)
                self.assertIsNone(app.hass.enable_kwargs)
                self.assertFalse(app.charge_controller.started)
                self.assertIsNotNone(app.charge_controller._main_current_guard)

    async def test_new_start_ignores_old_off_device_setpoint_without_erasing_readback(self):
        # Real node104 2026-11-27: OFF R18 but previous physical V/I setpoints
        # 2.4V/1.7A remain in the live controller. Detached constructor has None.
        # START must persist the *new requested* profile, not these old values.
        app = FakeApp(EnableResult(enabled=True))
        app.session_path = self.session_path
        live = app.charge_controller
        live._device_set_voltage = 2.4
        live._device_set_current = 1.7
        message = FakeMessage()

        outcome = await start_profile_transactional_result(app, message, PENDING)

        self.assertTrue(outcome.started, message.answers)
        self.assertEqual(outcome.persistence_status.value, "COMMITTED")
        self.assertEqual(live._device_set_voltage, 2.4)
        self.assertEqual(live._device_set_current, 1.7)
        self.assertAlmostEqual(app.hass.enable_kwargs["voltage_v"], 14.8)
        self.assertAlmostEqual(app.hass.enable_kwargs["current_a"], 7.0)
        document = json.loads(self.session_path.read_text(encoding="utf-8"))
        self.assertAlmostEqual(document["target_voltage"], 14.8)
        self.assertAlmostEqual(document["target_current"], 7.0)

    async def test_new_start_does_not_inherit_old_session_target_from_prior_document(self):
        # A retired/finished previous document can contain another program.
        # Even when new live telemetry has no setpoint, a NEW start must use
        # its new profile, not accidentally reuse a prior file's target.
        prior = b'{"stage": "DONE", "target_voltage": 2.4, "target_current": 1.7}\n'
        self.session_path.write_bytes(prior)
        app = FakeApp(EnableResult(enabled=True))
        app.session_path = self.session_path
        message = FakeMessage()

        outcome = await start_profile_transactional_result(app, message, PENDING)

        self.assertTrue(outcome.started, message.answers)
        self.assertAlmostEqual(app.hass.enable_kwargs["voltage_v"], 14.8)
        self.assertAlmostEqual(app.hass.enable_kwargs["current_a"], 7.0)
        document = json.loads(self.session_path.read_text(encoding="utf-8"))
        self.assertAlmostEqual(document["target_voltage"], 14.8)
        self.assertAlmostEqual(document["target_current"], 7.0)

    async def test_non_start_projection_still_preserves_fresh_observed_device_setpoints(self):
        # The new start flag is not a general override for ordinary saves.
        app = FakeApp(EnableResult(enabled=True))
        controller = app.charge_controller
        controller.start("EFB", 70, now_s=1000.0, clear_session=False)
        from runtime.charge.session import set_current_stage
        set_current_stage(controller, controller.STAGE_MAIN, now_s=1000.0)
        controller._device_set_voltage = 2.4
        controller._device_set_current = 1.7
        from runtime.charge.persistence import project_session_document
        regular = project_session_document(
            controller, 12.6, 0.0, 0.0,
            session_file=str(self.session_path), now_s=1000.0)
        new_start = project_session_document(
            controller, 12.6, 0.0, 0.0,
            session_file=str(self.session_path), now_s=1000.0,
            new_start_target=True)
        self.assertAlmostEqual(regular["target_voltage"], 2.4)
        self.assertAlmostEqual(regular["target_current"], 1.7)
        self.assertAlmostEqual(new_start["target_voltage"], 14.8)
        self.assertAlmostEqual(new_start["target_current"], 7.0)
        self.assertAlmostEqual(controller._device_set_voltage, 2.4)
        self.assertAlmostEqual(controller._device_set_current, 1.7)

    async def test_live_projection_parity_mismatch_rolls_back_before_enable(self):
        app = FakeApp(EnableResult(enabled=True))
        app.session_path = self.session_path
        prior = b'{ "stage": "DONE", "generation": 41 }\n'
        self.session_path.write_bytes(prior)
        app.execution_port.trace.clear()
        original = project_session_document_real
        calls = 0

        def mismatch_live(controller, *args, **kwargs):
            nonlocal calls
            calls += 1
            document = original(controller, *args, **kwargs)
            if calls == 2:
                document = dict(document)
                document["stage"] = "injected parity mismatch"
            return document

        with patch("runtime.charge.persistence.project_session_document",
                   side_effect=mismatch_live):
            ok = await start_profile_transactional(app, FakeMessage(), PENDING)

        self.assertFalse(ok)
        self.assertTrue(app.charge_controller.stopped)
        self.assertEqual(self.session_path.read_bytes(), prior)
        self.assertEqual(app.execution_port.off_calls, 0)
        self.assertEqual(app.execution_port.trace, [])

    async def test_fresh_start_retires_orphaned_pause_before_enabling_output(self):
        app = FakeApp(EnableResult(enabled=True))
        app.pause_active = True
        message = FakeMessage()

        ok = await start_profile_transactional(app, message, PENDING)

        self.assertTrue(ok)
        self.assertFalse(app.pause_active)
        self.assertTrue(app.charge_controller.started)
        self.assertEqual(app.events[0][-1], "OPERATOR_PAUSE_RETIRED_FOR_NEW_SESSION")
        self.assertIn("PREP_SKIPPED_INITIAL_VOLTAGE", app.events[-1][-1])

    async def test_orphaned_pause_without_clear_capability_fails_closed(self):
        app = FakeApp(EnableResult(enabled=True))
        app.pause_active = True
        app._clear_operator_pause = None
        message = FakeMessage()

        ok = await start_profile_transactional(app, message, PENDING)

        self.assertFalse(ok)
        self.assertFalse(app.charge_controller.started)
        self.assertIsNone(app.hass.enable_kwargs)
        self.assertIn("предыдущая пауза сессии не может быть безопасно сброшена", message.answers[-1][0])

    async def test_active_paused_session_is_not_retired_by_second_start(self):
        app = FakeApp(EnableResult(enabled=True))
        app.pause_active = True
        app.charge_controller.start("EFB", 70, clear_session=False)
        app.charge_controller.started = False
        message = FakeMessage()

        ok = await start_profile_transactional(app, message, PENDING)

        self.assertFalse(ok)
        self.assertTrue(app.pause_active)
        self.assertFalse(app.charge_controller.started)
        self.assertEqual(app.charge_controller.start_calls, 1)
        self.assertIsNone(app.hass.enable_kwargs)

    async def test_not_committed_pending_write_reports_not_attempted_only_with_exact_preimage(self):
        app = FakeApp(EnableResult(enabled=True))
        before = self.session_path.read_bytes() if self.session_path.exists() else None
        result = StartPendingResult(
            StartPendingStatus.NOT_COMMITTED, observed_raw=before, pending=None,
            reason="injected_definite_not_committed",
        )
        with patch("runtime.charge.persistence.begin_start_pending", return_value=result):
            outcome = await start_profile_transactional_result(app, FakeMessage(), PENDING)
        self.assertFalse(outcome.started)
        self.assertEqual(outcome.persistence_status.value, "NOT_ATTEMPTED")
        self.assertTrue(outcome.session_contained)
        self.assertIsNone(app.hass.enable_kwargs)

    async def test_typed_success_reports_commit_after_exact_durable_readback(self):
        app = FakeApp(EnableResult(enabled=True))
        outcome = await start_profile_transactional_result(app, FakeMessage(), PENDING)
        self.assertTrue(outcome.started)
        self.assertEqual(outcome.persistence_status.value, "COMMITTED")
        self.assertFalse(outcome.output_off_confirmed)
        self.assertFalse(outcome.session_contained)
        legacy = await start_profile_transactional(
            FakeApp(EnableResult(enabled=True)), FakeMessage(), PENDING,
        )
        self.assertIs(type(legacy), bool)

    async def test_failed_enable_rolls_controller_back_only_after_confirmed_off(self):
        app = FakeApp(
            EnableResult(
                enabled=False,
                violations=frozenset({SafetyViolation.READBACK_MISMATCH}),
                detail="setpoint readback mismatch",
            )
        )
        prior = b'{ "stage": "DONE", "profile": "EFB", "generation": 9 }\n'
        self.session_path.write_bytes(prior)
        message = FakeMessage()
        outcome = await start_profile_transactional_result(app, message, PENDING)
        self.assertFalse(outcome.started)
        self.assertEqual(outcome.persistence_status.value, "ROLLED_BACK")
        self.assertTrue(outcome.output_off_confirmed)
        self.assertTrue(app.charge_controller.stopped)
        self.assertEqual(app.execution_port.off_calls, 1)
        self.assertEqual(self.session_path.read_bytes(), prior)
        self.assertIn("подтверждён OFF", message.answers[-1][0])

    async def test_unconfirmed_off_keeps_controller_alive_and_warns_operator(self):
        app = FakeApp(
            EnableResult(
                enabled=False,
                violations=frozenset({SafetyViolation.OUTPUT_ENABLE_FAILED}),
                detail="output state unknown",
            )
        )
        app.execution_port.receipt_enabled = False
        message = FakeMessage()
        outcome = await start_profile_transactional_result(app, message, PENDING)
        self.assertFalse(outcome.started)
        self.assertEqual(outcome.persistence_status.value, "PENDING")
        self.assertTrue(outcome.output_off_unconfirmed)
        self.assertTrue(outcome.session_contained)
        self.assertTrue(app.charge_controller.is_active)
        self.assertFalse(app.charge_controller.stopped)
        self.assertTrue(app.execution_port.session_recovery_guard.quarantined)
        pending_bytes = self.session_path.read_bytes()
        self.assertIn(b"start_transaction_pending_v1", pending_bytes)
        self.assertIn("OFF не доказан", message.answers[-1][0])

    async def test_invalid_off_receipt_preserves_pending_and_quarantines(self):
        app = FakeApp(EnableResult(enabled=False, detail="enable outcome uncertain"))
        app.execution_port.receipt_override = OutputCommandReceipt(
            request_id="invalid-off-target", requested_target=True,
            terminal_status="APPLIED", observed_r18=0,
            terminal_completed_monotonic=time.monotonic() - 0.001,
            connection_generation=7, raw_terminal_identity="invalid-target",
        )
        message = FakeMessage()
        ok = await start_profile_transactional(app, message, PENDING)
        self.assertFalse(ok)
        self.assertEqual(app.execution_port.off_calls, 1)
        self.assertTrue(app.execution_port.session_recovery_guard.quarantined)
        self.assertTrue(app.charge_controller.is_active)
        self.assertIn(b"start_transaction_pending_v1", self.session_path.read_bytes())

    async def test_stale_native_generation_and_timestamp_preserve_pending(self):
        app = FakeApp(EnableResult(enabled=False, detail="enable outcome uncertain"))
        prior = b'{ "stage": "DONE", "profile": "EFB", "generation": 14 }\n'
        self.session_path.write_bytes(prior)

        app.hass.report_generation = 8
        app.hass.report_timestamp_override = time.monotonic() - 1.0
        message = FakeMessage()
        ok = await start_profile_transactional(app, message, PENDING)
        self.assertFalse(ok)
        self.assertEqual(app.execution_port.off_calls, 1)
        self.assertTrue(app.execution_port.session_recovery_guard.quarantined)
        self.assertTrue(app.charge_controller.is_active)
        self.assertIn(b"start_transaction_pending_v1", self.session_path.read_bytes())

    async def test_missing_native_off_reader_preserves_pending_and_quarantines(self):
        app = FakeApp(EnableResult(enabled=False, detail="enable outcome uncertain"))
        app.hass.get_native_physical_output_report = None
        message = FakeMessage()
        ok = await start_profile_transactional(app, message, PENDING)
        self.assertFalse(ok)
        self.assertEqual(app.execution_port.off_calls, 1)
        self.assertTrue(app.execution_port.session_recovery_guard.quarantined)
        self.assertTrue(app.charge_controller.is_active)
        self.assertIn(b"start_transaction_pending_v1", self.session_path.read_bytes())

    async def test_runner_state_save_failure_settles_off_and_restores_exact_prior_bytes(self):
        app = FakeApp(EnableResult(enabled=True))
        prior = b'{ "stage": "DONE", "profile": "EFB", "generation": 13 }\n'
        self.session_path.write_bytes(prior)
        recipe = types.SimpleNamespace(
            digest="recipe-digest",
            steps=[{"action": "set", "params": {"voltage_v": 14.4, "current_a": 1.0}}],
        )
        app._user_recipe_catalog = types.SimpleNamespace(
            library=types.SimpleNamespace(
                root=self.session_path.parent,
                load=lambda *_args: recipe,
            )
        )
        recipe_pending = types.SimpleNamespace(
            **vars(PENDING), recipe_id="recipe-1", recipe_version=1,
        )
        binding = types.SimpleNamespace(
            session=types.SimpleNamespace(recipe=recipe),
            state_path=self.session_path.parent / "runner.json",
        )
        with patch(
            "runtime.charge.programs.recipe_preflight.inspect_recipe",
            return_value=types.SimpleNamespace(admissible_structure=True, problems=()),
        ), patch(
            "application.recipe_existing_session.prepare_existing_recipe_binding",
            return_value=binding,
        ), patch(
            "runtime.charge.programs.recipe_runner_store.save_runner",
            side_effect=OSError("injected runner persistence failure"),
        ):
            ok = await start_profile_transactional(app, FakeMessage(), recipe_pending)

        self.assertFalse(ok)
        self.assertEqual(app.execution_port.off_calls, 1)
        self.assertEqual(self.session_path.read_bytes(), prior)
        self.assertTrue(app.charge_controller.stopped)
        self.assertFalse(app.execution_port.session_recovery_guard.quarantined)

    async def test_uncertain_commit_status_never_succeeds_when_candidate_was_written(self):
        app = FakeApp(EnableResult(enabled=True))
        prior = b'{ "stage": "DONE", "start_transaction_generation": 4 }\n'
        self.session_path.write_bytes(prior)
        message = FakeMessage()
        committed_bytes = None
        rollback_calls = 0
        commit_actions = []

        def commit_written_but_status_uncertain(expected_raw, pending, replacement=None, *,
                                                action=StartPendingAction.COMMIT, path=None):
            nonlocal committed_bytes, rollback_calls
            commit_actions.append(action)
            if action == StartPendingAction.ROLLBACK:
                rollback_calls += 1
            result = finish_start_pending_real(
                expected_raw, pending, replacement,
                action=action, path=path or self.session_path,
            )
            if action == StartPendingAction.COMMIT:
                committed_bytes = Path(path or self.session_path).read_bytes()
                return StartPendingResult(
                    StartPendingStatus.OUTCOME_UNCERTAIN,
                    observed_raw=result.observed_raw,
                    reason="injected_status_uncertain_after_atomic_write",
                )
            return result

        with patch("runtime.charge.persistence.finish_start_pending",
                   side_effect=commit_written_but_status_uncertain):
            outcome = await start_profile_transactional_result(app, message, PENDING)

        self.assertFalse(outcome.started)
        self.assertEqual(outcome.persistence_status.value, "OUTCOME_UNCERTAIN")
        self.assertTrue(outcome.output_off_confirmed)
        self.assertEqual(app.execution_port.off_calls, 1)
        self.assertEqual(commit_actions, [StartPendingAction.COMMIT], message.answers)
        self.assertEqual(rollback_calls, 0)
        self.assertGreaterEqual(app.hass.native_report_calls, 1)
        self.assertEqual(app.hass.last_native_report[0], 0)
        self.assertEqual(app.hass.last_native_report[1]["connection_generation"], 7)
        self.assertLessEqual(
            time.monotonic() - app.hass.last_native_report[1]["subscription_timestamp_monotonic"],
            8.0,
        )
        self.assertTrue(app.execution_port.session_recovery_guard.quarantined)
        self.assertFalse(app.charge_controller.is_active)
        self.assertTrue(app.charge_controller.stopped)
        self.assertFalse(any("Заряд запущен" in text
                             for text, _kwargs in message.answers))
        self.assertIsNotNone(committed_bytes)
        self.assertEqual(self.session_path.read_bytes(), committed_bytes)
        committed = json.loads(committed_bytes.decode("utf-8"))
        self.assertNotIn("start_transaction_pending_v1", committed)
        self.assertEqual(committed["start_transaction_generation"], 5)

    async def test_uncertain_candidate_commit_runs_off_then_exact_rollback(self):
        app = FakeApp(EnableResult(enabled=True))
        prior = b'{ "stage": "DONE", "profile": "EFB", "generation": 12 }\n'
        self.session_path.write_bytes(prior)

        rollback_calls = 0

        def commit_uncertain(expected_raw, pending, replacement=None, *,
                             action=StartPendingAction.COMMIT, path=None):
            nonlocal rollback_calls
            if action == StartPendingAction.COMMIT:
                return StartPendingResult(
                    StartPendingStatus.OUTCOME_UNCERTAIN,
                    reason="injected_commit_uncertain",
                )
            if action == StartPendingAction.ROLLBACK:
                rollback_calls += 1
            return finish_start_pending_real(
                expected_raw, pending, replacement,
                action=action, path=path or self.session_path,
            )

        with patch("runtime.charge.persistence.finish_start_pending",
                   side_effect=commit_uncertain):
            ok = await start_profile_transactional(app, FakeMessage(), PENDING)

        self.assertFalse(ok)
        self.assertEqual(app.execution_port.off_calls, 1)
        self.assertEqual(rollback_calls, 1)
        self.assertEqual(self.session_path.read_bytes(), prior)
        self.assertTrue(app.charge_controller.stopped)
        self.assertFalse(app.execution_port.session_recovery_guard.quarantined)

    async def test_typed_outcome_marks_failed_rollback_uncertain_after_verified_off(self):
        app = FakeApp(EnableResult(enabled=False, detail="enable failed"))
        def rollback_uncertain(expected_raw, pending, replacement=None, *,
                              action=StartPendingAction.COMMIT, path=None):
            if action == StartPendingAction.ROLLBACK:
                return StartPendingResult(StartPendingStatus.OUTCOME_UNCERTAIN,
                                          reason="injected rollback uncertainty")
            return finish_start_pending_real(expected_raw, pending, replacement,
                                             action=action, path=path or self.session_path)
        with patch("runtime.charge.persistence.finish_start_pending",
                   side_effect=rollback_uncertain):
            outcome = await start_profile_transactional_result(app, FakeMessage(), PENDING)
        self.assertFalse(outcome.started)
        self.assertEqual(outcome.persistence_status.value, "OUTCOME_UNCERTAIN")
        self.assertTrue(outcome.output_off_confirmed)
        self.assertTrue(outcome.session_contained)
        self.assertTrue(app.execution_port.session_recovery_guard.quarantined)

    async def test_cancelled_submitted_enable_settles_one_off_and_restores_exact_prior_bytes(self):
        app = FakeApp(EnableResult(enabled=True))
        prior = b'{ "stage": "DONE", "profile": "EFB" }\n'
        self.session_path.write_bytes(prior)
        app.execution_port.enable_gate = asyncio.Event()
        task = asyncio.create_task(
            start_profile_transactional_result(app, FakeMessage(), PENDING)
        )
        await asyncio.wait_for(app.execution_port.enable_started.wait(), timeout=2)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=3)
        self.assertEqual(app.execution_port.off_calls, 1)
        self.assertEqual(self.session_path.read_bytes(), prior)
        self.assertTrue(app.charge_controller.stopped)
        self.assertFalse(app.execution_port.session_recovery_guard.quarantined)

    async def test_repeated_cancellation_shields_the_same_off_settlement_task(self):
        app = FakeApp(EnableResult(enabled=True))
        prior = b'{ "stage": "DONE", "profile": "EFB", "generation": 4 }\n'
        self.session_path.write_bytes(prior)
        app.execution_port.enable_gate = asyncio.Event()
        app.execution_port.off_gate = asyncio.Event()
        task = asyncio.create_task(
            start_profile_transactional(app, FakeMessage(), PENDING)
        )
        await asyncio.wait_for(app.execution_port.enable_started.wait(), timeout=2)
        task.cancel()
        await asyncio.wait_for(app.execution_port.off_started.wait(), timeout=2)
        task.cancel()
        await asyncio.sleep(0)
        self.assertFalse(task.done())
        self.assertEqual(app.execution_port.off_calls, 1)
        app.execution_port.off_gate.set()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=3)
        self.assertEqual(app.execution_port.off_calls, 1)
        self.assertEqual(self.session_path.read_bytes(), prior)
        self.assertTrue(app.charge_controller.stopped)
        self.assertFalse(app.execution_port.session_recovery_guard.quarantined)

    async def test_missing_external_temperature_never_starts_controller(self):
        app = FakeApp(EnableResult(enabled=True))
        app.hass.live["temp_ext"] = "unavailable"
        message = FakeMessage()
        ok = await start_profile_transactional(app, message, PENDING)
        self.assertFalse(ok)
        self.assertFalse(app.charge_controller.started)
        self.assertIsNone(app.hass.enable_kwargs)

    async def test_missing_internal_temperature_never_starts_controller(self):
        app = FakeApp(EnableResult(enabled=True))
        app.hass.live["temp_int"] = None
        message = FakeMessage()
        ok = await start_profile_transactional(app, message, PENDING)
        self.assertFalse(ok)
        self.assertFalse(app.charge_controller.started)
        self.assertIsNone(app.hass.enable_kwargs)

    async def test_existing_output_on_never_starts_new_session(self):
        app = FakeApp(EnableResult(enabled=True))
        app.hass.live["switch"] = "on"
        message = FakeMessage()
        ok = await start_profile_transactional(app, message, PENDING)
        self.assertFalse(ok)
        self.assertFalse(app.charge_controller.started)
        self.assertIsNone(app.hass.enable_kwargs)


if __name__ == "__main__":
    unittest.main()
