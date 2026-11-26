"""Single application boundary for physical actions owned by V2.

The port deliberately contains no phase, program, or target-selection logic.
It accepts an already-created :class:`ExecutionIntent`, delegates to the
existing execution owner, verifies readback, and records the correlation envelope.
"""

from __future__ import annotations

import asyncio
import logging
from functools import wraps
from dataclasses import dataclass
from time import time
import time as _time
from typing import Any, Callable, Mapping, Optional

from rd6018_telemetry import canonical_programmed_readback, finite_float
from runtime.safety.output_policy import OutputRequest, SafetySupervisor, snapshot_from_live
from runtime.safety.runtime_guard import RuntimeSafetyError
from runtime.output.command_receipt import OutputCommandReceipt
from .safe_output_coordinator import SafeOutputCoordinator

from .execution_intent.models import ExecutionIntent
from .guard_execution_owner_lock import GuardExecutionOwnerLock
from .operator_recovery_clearance import VerifiedOffEvidence
from .session_recovery_guard import SessionRecoveryGuard


_clearance_logger = logging.getLogger('rd6018.recovery_clearance')

NATIVE_OFF_EVIDENCE_TIMEOUT_S = 10.0
NATIVE_OFF_EVIDENCE_POLL_INTERVAL_S = 0.20


def _serialized_normal_execution(method):
    """Serialize normal port work when this port has its production app lock."""
    @wraps(method)
    async def wrapped(self, *args, **kwargs):
        lock = self._guard_owner_lock
        if lock is None:
            return await method(self, *args, **kwargs)
        return await lock.run(lambda: method(self, *args, **kwargs))
    return wrapped


@dataclass(frozen=True)
class ExecutionPortAudit:
    intent_id: str
    decision_id: str
    session_id: str | None
    trace_id: str | None
    operation: str
    result: str
    reason: str
    timestamp: float


@dataclass(frozen=True)
class ExecutionPortResult:
    accepted: bool
    verified: bool
    operation: str
    reason: str
    audit: ExecutionPortAudit


@dataclass(frozen=True)
class ControllerActionExecutionResult:
    enabled: Optional[bool]
    final_verification_attempted: bool = False
    final_verification_failed: bool = False
    final_targets_missing: bool = False


@dataclass(frozen=True)
class GuardedPhysicalResumeResult:
    state: str
    reason: str
    receipt: Any = None


class ExecutionPort:
    """production physical port; never selects a phase or creates targets."""

    def __init__(
        self,
        execution_owner: Any,
        session_recovery_guard: SessionRecoveryGuard | None = None,
        *,
        app: Any = None,
    ) -> None:
        self._execution_owner = execution_owner
        self.app = app
        self.audit: list[ExecutionPortAudit] = []
        # UNBOUND by default: a stand-alone Guard transaction cannot grant
        # itself an independent lock and pretend it protects all output paths.
        self._guard_owner_lock: asyncio.Lock | None = None
        self.session_recovery_guard = session_recovery_guard or SessionRecoveryGuard()
        self._guarded_restore_activated_off = False
        self._guarded_resume_endpoint = None
        self._guarded_resume_consumed: set[int] = set()

    async def read_live(self) -> Mapping[str, Any]:
        """Read through the composed Safety owner without exposing that owner."""
        live = await self._execution_owner.get_all_live()
        if not isinstance(live, Mapping):
            raise RuntimeError("execution owner returned an invalid live snapshot")
        return live

    async def read_native_physical_output_report(self) -> Any:
        """Read native Output evidence through the composed Safety owner."""
        reader = getattr(self._execution_owner, "get_native_physical_output_report", None)
        if not callable(reader):
            return None
        return await reader()

    @property
    def guarded_restore_activated_off(self) -> bool:
        return self._guarded_restore_activated_off

    def mark_guarded_restore_activated_off(self) -> None:
        """Install the monotone block held until a later resume owner exists."""
        self._guarded_restore_activated_off = True

    async def execute_guarded_physical_resume(self, permit: Any) -> GuardedPhysicalResumeResult:
        """Consume a one-use lock-bound resume capability through an injected endpoint.

        Production intentionally has no endpoint installed in this source-only
        cut. Tests may inject a synthetic endpoint; a positive receipt is the
        sole authority that releases the OFF-only latch.
        """
        from runtime.charge.session import (
            GuardedPhysicalResumePermit, _GUARDED_PHYSICAL_RESUME_SEAL,
        )
        lock = self._guard_owner_lock
        task = asyncio.current_task()
        if (not isinstance(permit, GuardedPhysicalResumePermit)
                or permit._seal is not _GUARDED_PHYSICAL_RESUME_SEAL
                or lock is None or not lock.locked() or lock.owner_task is not task
                or getattr(permit, "owner_task", None) is not task
                or getattr(permit, "owner_lock", None) is not lock
                or not self.guarded_restore_activated_off):
            return GuardedPhysicalResumeResult("BLOCKED", "owner_or_latch_invalid")
        token = id(permit)
        if token in self._guarded_resume_consumed:
            return GuardedPhysicalResumeResult("BLOCKED", "permit_replayed")
        self._guarded_resume_consumed.add(token)
        endpoint = self._guarded_resume_endpoint
        if endpoint is None:
            return GuardedPhysicalResumeResult("READY_BUT_NOT_EXECUTED", "production_endpoint_disabled")
        try:
            receipt = await endpoint(permit)
        except Exception as exc:
            return GuardedPhysicalResumeResult("BLOCKED", "verified_on_failed:" + type(exc).__name__)
        if not getattr(receipt, "verified_on", False):
            return GuardedPhysicalResumeResult("BLOCKED", "verified_on_receipt_missing")
        # Single atomic source site: both owners release only after positive receipt.
        self._guarded_restore_activated_off = False
        controller = getattr(permit, "controller", None)
        if controller is not None:
            controller._guarded_restore_activated_off = False
        return GuardedPhysicalResumeResult("VERIFIED_ON_COMMITTED", "verified_on_receipt_committed", receipt)

    def _recovery_quarantined(self) -> bool:
        return self.session_recovery_guard.quarantined

    def _normal_actuation_gate(
        self,
        action: str,
        *,
        allow_startup_off_clearance: bool = False,
        ignore_startup: bool = False,
        allow_hands_off_operator_off: bool = False,
    ) -> None:
        """Apply ownership/startup policy before any normal physical action."""
        app = self.app
        if app is None:
            return
        manager = getattr(app, "rd_control_mode_manager", None)
        if manager is not None:
            hands_off = bool(getattr(manager, "hands_off", False))
            autonomous = bool(getattr(manager, "edge_autonomous", False))
            releasing = bool(getattr(manager, "release_in_progress", False))
            hands_off_off_override = (
                bool(allow_hands_off_operator_off)
                and action == "Output OFF"
                and hands_off
            )
            if (
                autonomous
                or (hands_off and not hands_off_off_override)
                or (releasing and action != "Output OFF")
            ):
                state = "RD AUTONOMOUS" if autonomous else (
                    "HANDS_OFF transfer" if releasing else "RD HANDS_OFF"
                )
                raise RuntimeSafetyError(
                    f"{state}: bot {action} is disabled; use the physical RD6018 controls"
                )

        if ignore_startup:
            return
        startup = getattr(app, "rd_startup_authority_gate", None)
        if startup is None or bool(getattr(startup, "recovery_scope", False)):
            return
        if bool(getattr(startup, "managed_actuation_ready", True)):
            return
        if allow_startup_off_clearance and action == "Output OFF":
            recovery_guard = getattr(app, "session_recovery_guard", None)
            quarantined = getattr(recovery_guard, "quarantined", False) is True
            candidate = getattr(startup, "candidate_autonomous", None)
            edge_auto = bool(getattr(manager, "edge_autonomous", False)) if manager is not None else False
            if quarantined and candidate is False and not edge_auto:
                return
        blocked = getattr(startup, "_blocked", None)
        if callable(blocked):
            raise blocked(action)
        raise RuntimeSafetyError(f"startup authority: bot {action} is blocked")

    def _authorize_adopted_write(self, field: str, value: float) -> tuple[Any, Any]:
        """Authorize adopted-live/MIX ratchets without touching the transport adapter."""
        app = self.app
        if app is None:
            return None, None
        mix = getattr(app, "rd_managed_mix_adoption", None)
        adoption = getattr(app, "rd_managed_live_adoption", None)
        if mix is not None:
            mix.authorize_managed_write(field, value)
        if adoption is not None:
            adoption.authorize_managed_write(field, value)
        return adoption, mix

    @staticmethod
    def _ratchet_adopted_write(authorities: tuple[Any, Any], field: str, value: float) -> None:
        adoption, mix = authorities
        if adoption is not None:
            adoption.ratchet_after_managed_write(field, value)
        if mix is not None:
            mix.ratchet_after_managed_write(field, value)

    def authorize_managed_start(self) -> None:
        """Authorize controller session creation before any START state mutation."""
        if self._recovery_quarantined() or self.guarded_restore_activated_off:
            raise RuntimeSafetyError("managed START blocked by recovery quarantine")
        self._normal_actuation_gate("automatic charge start")

    def _assert_output_on_authority(self) -> None:
        self._normal_actuation_gate("Output ON")
        app = self.app
        if app is None:
            return
        adoption = getattr(app, "rd_managed_live_adoption", None)
        if adoption is not None and (
            bool(getattr(adoption, "active", False))
            or bool(getattr(adoption, "off_pending", False))
        ):
            raise RuntimeSafetyError(
                "adopted-live Manual cannot re-energize Output; start a fresh managed program"
            )
        mix = getattr(app, "rd_managed_mix_adoption", None)
        if mix is not None and bool(getattr(mix, "managed_authority", False)):
            raise RuntimeSafetyError(
                "MIX_ADOPTED cannot re-energize Output; a fresh managed program is required"
            )

    def bind_guard_owner_lock(self, lock: GuardExecutionOwnerLock) -> None:
        """Bind the proven app-wide lifecycle lock before Guard activation.

        Integration must separately prove that controller/START/manual/recovery,
        physical writes and journal commits ALL participate in this lock.
        Binding alone does not provide that proof or activate MAIN Guard.
        """
        if self._guard_owner_lock is not None and self._guard_owner_lock is not lock:
            raise RuntimeError("guard owner lock already bound to a different lock")
        if not isinstance(lock, GuardExecutionOwnerLock):
            raise TypeError("owner lock must be GuardExecutionOwnerLock")
        self._guard_owner_lock = lock

    @_serialized_normal_execution
    async def enable(
        self,
        intent: ExecutionIntent,
        *,
        identity: Any,
        recipe_voltage_ceiling_v: float,
        on_receipt_observed: Optional[Callable[[OutputCommandReceipt], Any]] = None,
        on_native_phase_observed: Optional[Callable[[OutputCommandReceipt, Mapping[str, Any]], Any]] = None,
    ) -> ExecutionPortResult:
        if self._recovery_quarantined() or self.guarded_restore_activated_off:
            reason = ("guarded_restore_resume_gate_pending" if self.guarded_restore_activated_off
                      else "session_recovery_quarantined")
            return self._result(intent, identity, "enable", False, False, reason)
        from runtime.output.command_receipt_observation import (
            begin_observation, reset_observation,
        )
        observation, token = begin_observation()
        try:
            self._assert_output_on_authority()
            if callable(getattr(self._execution_owner, "safe_enable_output", None)):
                result = await self._execution_owner.safe_enable_output(
                    voltage_v=float(intent.requested_voltage_v),
                    current_a=float(intent.requested_current_a),
                    recipe_voltage_ceiling_v=float(recipe_voltage_ceiling_v),
                )
            else:
                policy = getattr(self._execution_owner, "policy", None)
                supervisor = SafetySupervisor(policy) if policy is not None else SafetySupervisor()
                coordinator = SafeOutputCoordinator(self._execution_owner, supervisor)
                result = await coordinator.enable(OutputRequest(
                    voltage_v=float(intent.requested_voltage_v),
                    current_a=float(intent.requested_current_a),
                    recipe_voltage_ceiling_v=float(recipe_voltage_ceiling_v),
                ))
            accepted = bool(getattr(result, "enabled", False))
            if accepted and on_receipt_observed is not None and observation.receipt is not None:
                try:
                    on_receipt_observed(observation.receipt)
                except Exception:
                    # Observation is ancillary; it cannot alter an accepted
                    # physical transaction or trigger another actuator call.
                    pass
            if accepted and on_native_phase_observed is not None and observation.receipt is not None:
                try:
                    reader = getattr(self._execution_owner, "get_post_on_native_phase", None)
                    phase = reader(observation.receipt) if callable(reader) else {
                        "status": "NOT_OBSERVED", "reason": "native_backend_unavailable",
                    }
                    on_native_phase_observed(observation.receipt, phase)
                except Exception:
                    # Ancillary phase evidence cannot affect the accepted ON path.
                    pass
            return self._result(
                intent, identity, "enable", accepted, accepted,
                str(getattr(result, "detail", "safe_enable_verified" if accepted else "safe_enable_rejected")),
            )
        except (AttributeError, RuntimeError, TypeError, ValueError):
            # The owning manual manager retains its existing containment policy
            # for enable exceptions; do not hide the exception here.
            raise
        finally:
            reset_observation(token)

    @_serialized_normal_execution
    async def apply_intent(self, intent: ExecutionIntent, *, identity: Any) -> ExecutionPortResult:
        if self._recovery_quarantined():
            return self._result(intent, identity, "setpoints", False, False, "session_recovery_quarantined")
        if not self._identity_valid(identity):
            return self._result(intent, identity, "setpoints", False, False, "identity_required")
        try:
            before = await self._execution_owner.get_all_live()
            battery_v = finite_float(before.get("battery_voltage"))
            output = str(before.get("switch", "")).lower() in {"on", "true", "1"}
            if not output or battery_v is None or intent.requested_voltage_v < battery_v:
                return self._result(intent, identity, "setpoints", False, False, "precondition_failed")
            if not await self.program_current(intent.requested_current_a):
                return self._result(intent, identity, "setpoints", False, False, "current_setter_rejected")
            if not await self.program_voltage(intent.requested_voltage_v):
                return self._result(intent, identity, "setpoints", False, False, "voltage_setter_rejected")
            after = await self._execution_owner.get_all_live()
            read_v = canonical_programmed_readback(after, "set_voltage")
            read_i = canonical_programmed_readback(after, "set_current")
            verified = (
                str(after.get("switch", "")).lower() in {"on", "true", "1"}
                and read_v is not None and read_i is not None
                and abs(read_v - intent.requested_voltage_v) <= 0.08
                and abs(read_i - intent.requested_current_a) <= 0.08
            )
            return self._result(intent, identity, "setpoints", verified, verified, "readback_verified" if verified else "readback_mismatch")
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            return self._result(intent, identity, "setpoints", False, False, type(exc).__name__)

    @_serialized_normal_execution
    async def execute_main_current_guard_reduction(self, **transaction: Any) -> Any:
        """Execute one due MAIN Guard current-setpoint reduction on this owner."""
        if self._recovery_quarantined():
            return None
        from .main_guard_transaction import execute_main_guard_reduction

        return await execute_main_guard_reduction(self, **transaction)

    @_serialized_normal_execution
    async def execute_desulfation_main_return(self, **transaction: Any) -> Any:
        """Run guarded DESULFATION -> MAIN restoration in the existing port."""
        if self._recovery_quarantined():
            return None
        from .main_guard_transaction import execute_main_guard_desulfation_return

        return await execute_main_guard_desulfation_return(
            self, execution_lock=self._guard_owner_lock, **transaction,
        )

    async def verify_live_programming(
        self,
        *,
        voltage_v: float,
        current_a: float,
        recipe_voltage_ceiling_v: float,
    ) -> bool:
        """Verify post-ON V/I and live safety without re-running pre-enable policy."""
        request = OutputRequest(
            voltage_v=float(voltage_v),
            current_a=float(current_a),
            recipe_voltage_ceiling_v=float(recipe_voltage_ceiling_v),
        )
        policy = getattr(self._execution_owner, "policy", None)
        supervisor = SafetySupervisor(policy) if policy is not None else SafetySupervisor()
        try:
            live = await self._execution_owner.get_all_live()
        except Exception:
            return False
        if not isinstance(live, Mapping):
            return False
        programmed = snapshot_from_live(
            live,
            require_programming_freshness=True,
        )
        if programmed is None:
            return False
        return bool(supervisor.verify_live_output(request, programmed).allowed)

    @_serialized_normal_execution
    async def request_verified_off(self) -> bool:
        """Delegate one verified Output-OFF transaction to the production owner."""
        self._normal_actuation_gate("Output OFF", allow_startup_off_clearance=True)
        return bool(await self._execution_owner.turn_off())

    async def request_emergency_off(
        self,
        entity_id: Optional[str] = None,
        *,
        allow_hands_off_operator_off: bool = False,
    ) -> bool:
        """Request guarded containment OFF without waiting for normal app work."""
        self._normal_actuation_gate(
            "Output OFF",
            ignore_startup=True,
            allow_hands_off_operator_off=allow_hands_off_operator_off,
        )
        if entity_id is None:
            return bool(await self._execution_owner.turn_off())
        return bool(await self._execution_owner.turn_off(entity_id))

    async def request_emergency_off_receipt(
        self,
        *,
        allow_hands_off_operator_off: bool = False,
        on_native_off_observed: Optional[Callable[[OutputCommandReceipt, Mapping[str, Any]], Any]] = None,
    ) -> OutputCommandReceipt | None:
        """Emergency liveness route returning exact AD051 OFF evidence when supported."""
        self._normal_actuation_gate(
            "Output OFF",
            ignore_startup=True,
            allow_hands_off_operator_off=allow_hands_off_operator_off,
        )
        operation = getattr(self._execution_owner, "turn_off_with_receipt", None)
        if not callable(operation):
            return None
        from runtime.output.command_receipt_observation import (
            begin_observation, reset_observation,
        )
        observation, token = begin_observation()
        try:
            try:
                receipt = await operation()
            except Exception:
                return None
            if not isinstance(receipt, OutputCommandReceipt):
                return None
            if on_native_off_observed is not None and observation.receipt is receipt:
                try:
                    reader = getattr(self._execution_owner, "get_post_on_native_phase", None)
                    sample = reader(receipt) if callable(reader) else {
                        "status": "NOT_OBSERVED", "reason": "native_backend_unavailable",
                    }
                    on_native_off_observed(receipt, sample)
                except Exception:
                    # Ancillary readback cannot affect emergency OFF semantics.
                    pass
            return receipt
        finally:
            reset_observation(token)

    @_serialized_normal_execution
    async def request_verified_off_evidence(self) -> VerifiedOffEvidence | None:
        """Clearance-only proof from a post-completion native ESPHome callback."""
        import math
        # Clearance returns only a typed OFF receipt on success. On failure,
        # retain a bounded diagnostic reason for the operator UI; this is
        # never usable as evidence or authorization to resume charging.
        self.last_off_clearance_failure = None
        try:
            off_ok = await self.request_verified_off()
        except Exception as exc:
            reason = " ".join(str(exc).split())[:120]
            self.last_off_clearance_failure = (
                "turn_off_" + type(exc).__name__ +
                (": " + reason if reason else "")
            )
            _clearance_logger.warning("CLEARANCE_OFF_FAILED step=turn_off_exception type=%s detail=%s", type(exc).__name__, str(exc)[:240])
            return None
        if not off_ok:
            self.last_off_clearance_failure = "turn_off_rejected"
            _clearance_logger.warning("CLEARANCE_OFF_FAILED step=turn_off_rejected")
            return None
        off_completed_at = _time.monotonic()
        reader = getattr(self._execution_owner, "get_native_physical_output_report", None)
        if not callable(reader):
            self.last_off_clearance_failure = "native_reader_missing"
            _clearance_logger.warning("CLEARANCE_OFF_FAILED step=native_reader_missing")
            return None
        deadline = asyncio.get_running_loop().time() + NATIVE_OFF_EVIDENCE_TIMEOUT_S
        last_reason = "no_native_report"
        while True:
            try:
                report = await reader()
            except Exception as exc:
                last_reason = 'native_reader_exception:' + type(exc).__name__
                report = None
            if isinstance(report, tuple) and len(report) == 2:
                value, meta = report
                if isinstance(meta, Mapping):
                    timestamp = meta.get("subscription_timestamp_monotonic")
                    age = meta.get("age_s")
                    def finite_number(candidate: Any) -> float | None:
                        if isinstance(candidate, bool) or not isinstance(candidate, (int, float)):
                            return None
                        try:
                            number = float(candidate)
                        except (TypeError, ValueError, OverflowError):
                            return None
                        return number if math.isfinite(number) else None

                    timestamp_value = finite_number(timestamp)
                    age_value = finite_number(age)
                    output_value = finite_number(value)
                    valid_timestamp = (
                        timestamp_value is not None and timestamp_value > off_completed_at
                    )
                    valid_age = age_value is not None and 0 <= age_value <= 8.0
                    fresh_by_clock = (valid_timestamp and
                                      0 <= _time.monotonic() - timestamp_value <= 8.0)
                    valid_value = output_value == 0.0
                    if (valid_value and valid_timestamp and fresh_by_clock and valid_age
                            and meta.get("native_type") == "SensorState"
                            and str(meta.get("status", "")).lower() == "ok"):
                        return VerifiedOffEvidence(f"execution-port-off:{_time.time_ns()}", _time.monotonic())
                    last_reason = (
                        "native_state_invalid" if not valid_value else
                        "no_post_off_callback" if not valid_timestamp else
                        "native_callback_stale" if not (fresh_by_clock and valid_age) else
                        "native_type_or_status_invalid"
                    )
            if asyncio.get_running_loop().time() >= deadline:
                self.last_off_clearance_failure = "native_evidence_timeout:" + last_reason
                _clearance_logger.warning("CLEARANCE_OFF_FAILED step=native_evidence_timeout reason=%s", last_reason)
                return None
            await asyncio.sleep(min(NATIVE_OFF_EVIDENCE_POLL_INTERVAL_S,
                                    max(0.0, deadline - asyncio.get_running_loop().time())))

    @_serialized_normal_execution
    async def request_verified_on(self) -> bool:
        """Delegate one guarded/verified Output-ON transaction to the V2 owner."""
        if self._recovery_quarantined() or self.guarded_restore_activated_off:
            return False
        self._assert_output_on_authority()
        return bool(await self._execution_owner.turn_on())

    @_serialized_normal_execution
    async def program_voltage(self, value_v: float) -> bool:
        if self._recovery_quarantined():
            return False
        value = float(value_v)
        self._normal_actuation_gate("voltage write")
        authorities = self._authorize_adopted_write("set_voltage_v", value)
        ok = bool(await self._execution_owner.set_voltage(value))
        if ok:
            self._ratchet_adopted_write(authorities, "set_voltage_v", value)
        return ok

    @_serialized_normal_execution
    async def program_current(self, value_a: float) -> bool:
        if self._recovery_quarantined():
            return False
        value = float(value_a)
        self._normal_actuation_gate("current write")
        authorities = self._authorize_adopted_write("set_current_a", value)
        ok = bool(await self._execution_owner.set_current(value))
        if ok:
            self._ratchet_adopted_write(authorities, "set_current_a", value)
        return ok

    @_serialized_normal_execution
    async def program_voltage_current(self, voltage_v: float, current_a: float) -> tuple[bool, bool]:
        """Keep manual V/I pair indivisible against other normal port calls.

        This is NOT a new Output ON authority. Uses existing setters and
        intentionally preserves their ordering and failure results.
        """
        if self._recovery_quarantined():
            return False, False
        ok_v = await self.program_voltage(voltage_v)
        ok_i = await self.program_current(current_a)
        return ok_v, ok_i

    @_serialized_normal_execution
    async def execute_controller_actions(
        self,
        actions: Mapping[str, Any],
        live: Mapping[str, Any],
        *,
        max_stage_current_a: float,
        recipe_voltage_ceiling_v: float,
    ) -> ControllerActionExecutionResult:
        """Execute the controller's V/I/Output actions through the existing owner."""
        if self._recovery_quarantined():
            if actions.get("turn_off"):
                await self.request_verified_off()
            return ControllerActionExecutionResult(enabled=False if actions.get("turn_on") else None)

        if actions.get("turn_off"):
            await self.request_verified_off()
        if actions.get("set_voltage") is not None:
            await self.program_voltage(float(actions["set_voltage"]))

        target_i = actions.get("set_current")
        if target_i is not None:
            target_i = min(float(max_stage_current_a), max(0.1, float(target_i)))
            await self.program_current(target_i)

        enabled: Optional[bool] = None
        if actions.get("turn_on"):
            enabled = await self.request_verified_on()

        attempted = failed = missing = False
        if enabled:
            attempted = True
            target_v = actions.get("set_voltage")
            if target_v is None or target_i is None:
                missing = True
                await self.request_emergency_off()
                enabled = False
            else:
                final_ok = await self.verify_live_programming(
                    voltage_v=float(target_v),
                    current_a=float(target_i),
                    recipe_voltage_ceiling_v=float(recipe_voltage_ceiling_v),
                )
                if not final_ok:
                    failed = True
                    await self.request_emergency_off()
                    enabled = False

        return ControllerActionExecutionResult(
            enabled=enabled,
            final_verification_attempted=attempted,
            final_verification_failed=failed,
            final_targets_missing=missing,
        )

    async def disable(self, intent: ExecutionIntent, *, identity: Any = None, reason: str = "requested_disable") -> ExecutionPortResult:
        # Verified OFF remains available for legacy/containment paths without
        # inventing a lifecycle identity. The audit explicitly records that gap.
        try:
            accepted = await self.request_verified_off()
            live = await self._execution_owner.get_all_live()
            output_off = self._output_is_off(live)
            verified = accepted and output_off
            return self._result(intent, identity, "disable", accepted, verified, reason if verified else "off_verification_failed")
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            return self._result(intent, identity, "disable", False, False, type(exc).__name__)

    @staticmethod
    def _identity_valid(identity: Any) -> bool:
        return bool(identity is not None and getattr(identity, "session_id", "") and getattr(identity, "trace_id", ""))

    @staticmethod
    def _output_is_off(live: Any) -> bool:
        if not isinstance(live, dict):
            return False
        code = live.get("output_state_code_v2")
        if code not in (None, "", "unknown", "unavailable"):
            try:
                return float(code) == 0.0
            except (TypeError, ValueError):
                return False
        return str(live.get("switch", "")).strip().lower() in {"off", "false", "0"}

    def _result(self, intent: ExecutionIntent, identity: Any, operation: str, accepted: bool, verified: bool, reason: str) -> ExecutionPortResult:
        audit = ExecutionPortAudit(
            intent_id=intent.intent_id,
            decision_id=intent.source_decision_id,
            session_id=getattr(identity, "session_id", None),
            trace_id=getattr(identity, "trace_id", None),
            operation=operation,
            result="VERIFIED" if verified else ("ACCEPTED" if accepted else "DENIED"),
            reason=reason,
            timestamp=time(),
        )
        self.audit.append(audit)
        return ExecutionPortResult(accepted, verified, operation, reason, audit)


def get_or_create_execution_port(app: Any) -> ExecutionPort:
    """Return the one application-scoped port bound to the current execution owner."""
    recovery_guard = getattr(app, "session_recovery_guard", None)
    if not isinstance(recovery_guard, SessionRecoveryGuard):
        recovery_guard = SessionRecoveryGuard()
        setattr(app, "session_recovery_guard", recovery_guard)
    owner = getattr(app, "runtime_safety_guard", None) or getattr(app, "hass", None)
    existing = getattr(app, "execution_port", None)
    if isinstance(existing, ExecutionPort) and existing._execution_owner is owner:
        existing.session_recovery_guard = recovery_guard
        existing.app = app
        lock = getattr(app, "guard_execution_owner_lock", None)
        if lock is None:
            lock = GuardExecutionOwnerLock()
            setattr(app, "guard_execution_owner_lock", lock)
        existing.bind_guard_owner_lock(lock)
        return existing
    port = ExecutionPort(owner, recovery_guard, app=app)
    lock = getattr(app, "guard_execution_owner_lock", None)
    if lock is None:
        lock = GuardExecutionOwnerLock()
        setattr(app, "guard_execution_owner_lock", lock)
    port.bind_guard_owner_lock(lock)
    setattr(app, "execution_port", port)
    return port


__all__ = [
    "ControllerActionExecutionResult",
    "ExecutionPort",
    "ExecutionPortAudit",
    "ExecutionPortResult",
    "get_or_create_execution_port",
]
