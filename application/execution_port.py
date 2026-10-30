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
from typing import Any, Mapping, Optional

from protection_utils import should_delay_current_ramp, should_use_startup_settle
from rd6018_telemetry import canonical_programmed_readback, finite_float

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

    def __init__(self, execution_owner: Any, session_recovery_guard: SessionRecoveryGuard | None = None) -> None:
        self.execution_owner = execution_owner
        self.audit: list[ExecutionPortAudit] = []
        # UNBOUND by default: a stand-alone Guard transaction cannot grant
        # itself an independent lock and pretend it protects all output paths.
        self._guard_owner_lock: asyncio.Lock | None = None
        self.session_recovery_guard = session_recovery_guard or SessionRecoveryGuard()
        self._guarded_restore_activated_off = False
        self._guarded_resume_endpoint = None
        self._guarded_resume_consumed: set[int] = set()

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
        ovp_v: float,
        ocp_a: float,
        recipe_voltage_ceiling_v: float,
    ) -> ExecutionPortResult:
        if self._recovery_quarantined() or self.guarded_restore_activated_off:
            reason = ("guarded_restore_resume_gate_pending" if self.guarded_restore_activated_off
                      else "session_recovery_quarantined")
            return self._result(intent, identity, "enable", False, False, reason)
        try:
            result = await self.execution_owner.safe_enable_output(
                voltage_v=float(intent.requested_voltage_v),
                current_a=float(intent.requested_current_a),
                ovp_v=float(ovp_v),
                ocp_a=float(ocp_a),
                recipe_voltage_ceiling_v=float(recipe_voltage_ceiling_v),
            )
            accepted = bool(getattr(result, "enabled", False))
            return self._result(
                intent, identity, "enable", accepted, accepted,
                str(getattr(result, "detail", "safe_enable_verified" if accepted else "safe_enable_rejected")),
            )
        except (AttributeError, RuntimeError, TypeError, ValueError):
            # The owning manual manager retains its existing containment policy
            # for enable exceptions; do not hide the exception here.
            raise

    @_serialized_normal_execution
    async def apply_intent(self, intent: ExecutionIntent, *, identity: Any) -> ExecutionPortResult:
        if self._recovery_quarantined():
            return self._result(intent, identity, "setpoints", False, False, "session_recovery_quarantined")
        if not self._identity_valid(identity):
            return self._result(intent, identity, "setpoints", False, False, "identity_required")
        try:
            before = await self.execution_owner.get_all_live()
            battery_v = finite_float(before.get("battery_voltage"))
            output = str(before.get("switch", "")).lower() in {"on", "true", "1"}
            if not output or battery_v is None or intent.requested_voltage_v < battery_v:
                return self._result(intent, identity, "setpoints", False, False, "precondition_failed")
            if not await self.execution_owner.set_current(intent.requested_current_a):
                return self._result(intent, identity, "setpoints", False, False, "current_setter_rejected")
            if not await self.execution_owner.set_voltage(intent.requested_voltage_v):
                return self._result(intent, identity, "setpoints", False, False, "voltage_setter_rejected")
            after = await self.execution_owner.get_all_live()
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
        """Opt-in MAIN Guard current/OCP transaction on the same execution owner.

        No production caller is installed. Persist/lock/readback authority must
        be supplied by the canonical runtime before enabling this path.
        """
        if self._recovery_quarantined():
            return None
        from .main_guard_transaction import execute_main_guard_reduction

        return await execute_main_guard_reduction(self, **transaction)

    async def request_verified_off(self) -> bool:
        """Delegate one verified Output-OFF transaction to the production owner."""
        return bool(await self.execution_owner.turn_off())

    @_serialized_normal_execution
    async def request_verified_off_evidence(self) -> VerifiedOffEvidence | None:
        """Clearance-only proof from a post-completion native ESPHome callback."""
        import math
        try:
            off_ok = await self.request_verified_off()
        except Exception as exc:
            _clearance_logger.warning("CLEARANCE_OFF_FAILED step=turn_off_exception type=%s detail=%s", type(exc).__name__, str(exc)[:240])
            return None
        if not off_ok:
            _clearance_logger.warning("CLEARANCE_OFF_FAILED step=turn_off_rejected")
            return None
        off_completed_at = _time.monotonic()
        reader = getattr(self.execution_owner, "get_native_physical_output_report", None)
        if not callable(reader):
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
                _clearance_logger.warning("CLEARANCE_OFF_FAILED step=native_evidence_timeout reason=%s", last_reason)
                return None
            await asyncio.sleep(min(NATIVE_OFF_EVIDENCE_POLL_INTERVAL_S,
                                    max(0.0, deadline - asyncio.get_running_loop().time())))

    @_serialized_normal_execution
    async def request_verified_on(self) -> bool:
        """Delegate one guarded/verified Output-ON transaction to the V2 owner."""
        if self._recovery_quarantined() or self.guarded_restore_activated_off:
            return False
        return bool(await self.execution_owner.turn_on())

    @_serialized_normal_execution
    async def program_voltage(self, value_v: float) -> bool:
        if self._recovery_quarantined():
            return False
        return bool(await self.execution_owner.set_voltage(float(value_v)))

    @_serialized_normal_execution
    async def program_current(self, value_a: float) -> bool:
        if self._recovery_quarantined():
            return False
        return bool(await self.execution_owner.set_current(float(value_a)))

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
    async def program_ovp(self, value_v: float) -> bool:
        if self._recovery_quarantined():
            return False
        return bool(await self.execution_owner.set_ovp(float(value_v)))

    @_serialized_normal_execution
    async def program_ocp(self, value_a: float) -> bool:
        if self._recovery_quarantined():
            return False
        return bool(await self.execution_owner.set_ocp(float(value_a)))

    @_serialized_normal_execution
    async def apply_phase_protection(
        self,
        *,
        target_voltage_v: float,
        target_current_a: float,
        ovp_offset_v: float,
        ocp_offset_a: float,
        max_stage_current_a: float,
        has_ovp: bool,
        has_ocp: bool,
    ) -> None:
        if self._recovery_quarantined():
            return
        if has_ovp:
            await self.execution_owner.set_ovp(float(target_voltage_v) + float(ovp_offset_v))
        if has_ocp:
            current = min(float(max_stage_current_a), max(0.1, float(target_current_a)))
            await self.execution_owner.set_ocp(current + float(ocp_offset_a))

    @_serialized_normal_execution
    async def apply_current_with_ocp(
        self,
        *,
        target_current_a: float,
        current_set_a: float,
        target_ocp_a: Optional[float],
        max_stage_current_a: float,
        ocp_offset_a: float,
        has_ocp: bool,
        stabilize_delay_s: float,
    ) -> None:
        if self._recovery_quarantined():
            return
        target_i = min(float(max_stage_current_a), max(0.1, float(target_current_a)))
        if target_ocp_a is None or not has_ocp:
            await self.execution_owner.set_current(target_i)
            return

        target_ocp = min(
            float(target_ocp_a),
            float(max_stage_current_a) + float(ocp_offset_a),
        )
        if target_i < float(current_set_a):
            await self.execution_owner.set_current(target_i)
            await self.execution_owner.set_ocp(target_ocp)
        elif should_delay_current_ramp(
            target_i,
            float(current_set_a),
            float(target_ocp_a),
            True,
        ):
            await self.execution_owner.set_ocp(target_ocp)
            await asyncio.sleep(float(stabilize_delay_s))
            await self.execution_owner.set_current(target_i)
        else:
            await self.execution_owner.set_ocp(target_ocp)
            await self.execution_owner.set_current(target_i)

    @_serialized_normal_execution
    async def apply_current_with_startup_settle(
        self,
        *,
        target_current_a: float,
        current_set_a: float,
        target_ocp_a: Optional[float],
        turn_on_requested: bool,
        max_stage_current_a: float,
        ocp_offset_a: float,
        idle_safe_ocp_a: float,
        has_ocp: bool,
        stabilize_delay_s: float,
    ) -> Optional[float]:
        if self._recovery_quarantined():
            return None
        target_i = min(float(max_stage_current_a), max(0.1, float(target_current_a)))
        if target_ocp_a is None or not has_ocp:
            await self.execution_owner.set_current(target_i)
            return None

        target_ocp = min(
            float(target_ocp_a),
            float(max_stage_current_a) + float(ocp_offset_a),
        )
        if should_use_startup_settle(
            target_i,
            float(current_set_a),
            float(target_ocp_a),
            True,
            bool(turn_on_requested),
        ):
            await self.execution_owner.set_ocp(float(idle_safe_ocp_a))
            await self.execution_owner.set_current(target_i)
            return target_ocp

        if target_i < float(current_set_a):
            await self.execution_owner.set_current(target_i)
            await self.execution_owner.set_ocp(target_ocp)
        elif should_delay_current_ramp(
            target_i,
            float(current_set_a),
            float(target_ocp_a),
            True,
        ):
            await self.execution_owner.set_ocp(target_ocp)
            await asyncio.sleep(float(stabilize_delay_s))
            await self.execution_owner.set_current(target_i)
        else:
            await self.execution_owner.set_ocp(target_ocp)
            await self.execution_owner.set_current(target_i)
        return None

    @_serialized_normal_execution
    async def reset_idle_protection(
        self,
        *,
        idle_safe_ovp_v: float,
        idle_safe_ocp_a: float,
        has_ovp: bool,
        has_ocp: bool,
    ) -> None:
        if self._recovery_quarantined():
            return
        if has_ovp:
            await self.execution_owner.set_ovp(float(idle_safe_ovp_v))
        if has_ocp:
            await self.execution_owner.set_ocp(float(idle_safe_ocp_a))

    @_serialized_normal_execution
    async def execute_controller_actions(
        self,
        actions: Mapping[str, Any],
        live: Mapping[str, Any],
        *,
        max_stage_current_a: float,
        ocp_offset_a: float,
        idle_safe_ocp_a: float,
        stabilize_delay_s: float,
        recipe_voltage_ceiling_v: float,
        has_ovp: bool,
        has_ocp: bool,
    ) -> ControllerActionExecutionResult:
        """Execute an already-decided controller action batch without stage logic."""

        if self._recovery_quarantined():
            # Preserve an explicit OFF action, then suppress every other write.
            if actions.get("turn_off"):
                await self.request_verified_off()
            return ControllerActionExecutionResult(enabled=False if actions.get("turn_on") else None)

        if actions.get("turn_off"):
            await self.request_verified_off()

        if actions.get("set_ovp") is not None and has_ovp:
            await self.execution_owner.set_ovp(float(actions["set_ovp"]))
        if actions.get("set_voltage") is not None:
            await self.execution_owner.set_voltage(float(actions["set_voltage"]))

        target_i_raw = actions.get("set_current")
        target_ocp_raw = actions.get("set_ocp")
        target_i: Optional[float] = None
        pending_ocp_restore: Optional[float] = None
        if target_i_raw is not None:
            target_i = min(
                float(max_stage_current_a),
                max(0.1, float(target_i_raw)),
            )
            try:
                current_set_i = float(live.get("set_current", target_i))
            except (TypeError, ValueError):
                current_set_i = target_i
            pending_ocp_restore = await self.apply_current_with_startup_settle(
                target_current_a=target_i,
                current_set_a=current_set_i,
                target_ocp_a=(
                    float(target_ocp_raw)
                    if target_ocp_raw is not None and has_ocp
                    else None
                ),
                turn_on_requested=bool(actions.get("turn_on")),
                max_stage_current_a=float(max_stage_current_a),
                ocp_offset_a=float(ocp_offset_a),
                idle_safe_ocp_a=float(idle_safe_ocp_a),
                has_ocp=bool(has_ocp),
                stabilize_delay_s=float(stabilize_delay_s),
            )
        elif target_ocp_raw is not None and has_ocp:
            target_ocp = min(
                float(target_ocp_raw),
                float(max_stage_current_a) + float(ocp_offset_a),
            )
            await self.execution_owner.set_ocp(target_ocp)

        enabled: Optional[bool] = None
        if actions.get("turn_on"):
            enabled = await self.request_verified_on()

        attempted = False
        failed = False
        missing = False
        if pending_ocp_restore is not None:
            await asyncio.sleep(float(stabilize_delay_s))
            await self.execution_owner.set_ocp(float(pending_ocp_restore))
            if enabled:
                attempted = True
                target_v_raw = actions.get("set_voltage")
                target_ovp_raw = actions.get("set_ovp")
                if target_v_raw is None or target_i is None or target_ovp_raw is None:
                    missing = True
                    await self.request_verified_off()
                    enabled = False
                else:
                    final_ok = await self.execution_owner.verify_live_programming(
                        voltage_v=float(target_v_raw),
                        current_a=float(target_i),
                        ovp_v=float(target_ovp_raw),
                        ocp_a=float(pending_ocp_restore),
                        recipe_voltage_ceiling_v=float(recipe_voltage_ceiling_v),
                    )
                    if not final_ok:
                        failed = True
                        await self.request_verified_off()
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
            live = await self.execution_owner.get_all_live()
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
    owner = getattr(app, "hass", None)
    existing = getattr(app, "execution_port", None)
    if isinstance(existing, ExecutionPort) and existing.execution_owner is owner:
        existing.session_recovery_guard = recovery_guard
        lock = getattr(app, "guard_execution_owner_lock", None)
        if lock is None:
            lock = GuardExecutionOwnerLock()
            setattr(app, "guard_execution_owner_lock", lock)
        existing.bind_guard_owner_lock(lock)
        return existing
    port = ExecutionPort(owner, recovery_guard)
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
