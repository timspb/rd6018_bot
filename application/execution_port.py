"""Single application boundary for physical actions owned by V2.

The port deliberately contains no phase, program, or target-selection logic.
It accepts an already-created :class:`ExecutionIntent`, delegates to the
existing V2 owner, verifies readback, and records the correlation envelope.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import time
from typing import Any, Mapping, Optional

from protection_utils import should_delay_current_ramp, should_use_startup_settle
from rd6018_telemetry import canonical_programmed_readback, finite_float

from .execution_intent.models import ExecutionIntent


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


class ExecutionPort:
    """V2-owned physical port; never selects a phase or creates targets."""

    def __init__(self, v2_owner: Any) -> None:
        self.v2_owner = v2_owner
        self.audit: list[ExecutionPortAudit] = []

    async def enable(
        self,
        intent: ExecutionIntent,
        *,
        identity: Any,
        ovp_v: float,
        ocp_a: float,
        recipe_voltage_ceiling_v: float,
    ) -> ExecutionPortResult:
        try:
            result = await self.v2_owner.safe_enable_output(
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

    async def apply_intent(self, intent: ExecutionIntent, *, identity: Any) -> ExecutionPortResult:
        if not self._identity_valid(identity):
            return self._result(intent, identity, "setpoints", False, False, "identity_required")
        try:
            before = await self.v2_owner.get_all_live()
            battery_v = finite_float(before.get("battery_voltage"))
            output = str(before.get("switch", "")).lower() in {"on", "true", "1"}
            if not output or battery_v is None or intent.requested_voltage_v < battery_v:
                return self._result(intent, identity, "setpoints", False, False, "precondition_failed")
            if not await self.v2_owner.set_current(intent.requested_current_a):
                return self._result(intent, identity, "setpoints", False, False, "current_setter_rejected")
            if not await self.v2_owner.set_voltage(intent.requested_voltage_v):
                return self._result(intent, identity, "setpoints", False, False, "voltage_setter_rejected")
            after = await self.v2_owner.get_all_live()
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

    async def request_verified_off(self) -> bool:
        """Delegate one verified Output-OFF transaction to the preserved V2 owner."""
        return bool(await self.v2_owner.turn_off())

    async def request_verified_on(self) -> bool:
        """Delegate one guarded/verified Output-ON transaction to the V2 owner."""
        return bool(await self.v2_owner.turn_on())

    async def program_voltage(self, value_v: float) -> bool:
        return bool(await self.v2_owner.set_voltage(float(value_v)))

    async def program_current(self, value_a: float) -> bool:
        return bool(await self.v2_owner.set_current(float(value_a)))

    async def program_ovp(self, value_v: float) -> bool:
        return bool(await self.v2_owner.set_ovp(float(value_v)))

    async def program_ocp(self, value_a: float) -> bool:
        return bool(await self.v2_owner.set_ocp(float(value_a)))

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
        if has_ovp:
            await self.v2_owner.set_ovp(float(target_voltage_v) + float(ovp_offset_v))
        if has_ocp:
            current = min(float(max_stage_current_a), max(0.1, float(target_current_a)))
            await self.v2_owner.set_ocp(current + float(ocp_offset_a))

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
        target_i = min(float(max_stage_current_a), max(0.1, float(target_current_a)))
        if target_ocp_a is None or not has_ocp:
            await self.v2_owner.set_current(target_i)
            return

        target_ocp = min(
            float(target_ocp_a),
            float(max_stage_current_a) + float(ocp_offset_a),
        )
        if target_i < float(current_set_a):
            await self.v2_owner.set_current(target_i)
            await self.v2_owner.set_ocp(target_ocp)
        elif should_delay_current_ramp(
            target_i,
            float(current_set_a),
            float(target_ocp_a),
            True,
        ):
            await self.v2_owner.set_ocp(target_ocp)
            await asyncio.sleep(float(stabilize_delay_s))
            await self.v2_owner.set_current(target_i)
        else:
            await self.v2_owner.set_ocp(target_ocp)
            await self.v2_owner.set_current(target_i)

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
        target_i = min(float(max_stage_current_a), max(0.1, float(target_current_a)))
        if target_ocp_a is None or not has_ocp:
            await self.v2_owner.set_current(target_i)
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
            await self.v2_owner.set_ocp(float(idle_safe_ocp_a))
            await self.v2_owner.set_current(target_i)
            return target_ocp

        if target_i < float(current_set_a):
            await self.v2_owner.set_current(target_i)
            await self.v2_owner.set_ocp(target_ocp)
        elif should_delay_current_ramp(
            target_i,
            float(current_set_a),
            float(target_ocp_a),
            True,
        ):
            await self.v2_owner.set_ocp(target_ocp)
            await asyncio.sleep(float(stabilize_delay_s))
            await self.v2_owner.set_current(target_i)
        else:
            await self.v2_owner.set_ocp(target_ocp)
            await self.v2_owner.set_current(target_i)
        return None

    async def reset_idle_protection(
        self,
        *,
        idle_safe_ovp_v: float,
        idle_safe_ocp_a: float,
        has_ovp: bool,
        has_ocp: bool,
    ) -> None:
        if has_ovp:
            await self.v2_owner.set_ovp(float(idle_safe_ovp_v))
        if has_ocp:
            await self.v2_owner.set_ocp(float(idle_safe_ocp_a))

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

        if actions.get("turn_off"):
            await self.request_verified_off()

        if actions.get("set_ovp") is not None and has_ovp:
            await self.v2_owner.set_ovp(float(actions["set_ovp"]))
        if actions.get("set_voltage") is not None:
            await self.v2_owner.set_voltage(float(actions["set_voltage"]))

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
            await self.v2_owner.set_ocp(target_ocp)

        enabled: Optional[bool] = None
        if actions.get("turn_on"):
            enabled = await self.request_verified_on()

        attempted = False
        failed = False
        missing = False
        if pending_ocp_restore is not None:
            await asyncio.sleep(float(stabilize_delay_s))
            await self.v2_owner.set_ocp(float(pending_ocp_restore))
            if enabled:
                attempted = True
                target_v_raw = actions.get("set_voltage")
                target_ovp_raw = actions.get("set_ovp")
                if target_v_raw is None or target_i is None or target_ovp_raw is None:
                    missing = True
                    await self.request_verified_off()
                    enabled = False
                else:
                    final_ok = await self.v2_owner.verify_live_programming(
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
            live = await self.v2_owner.get_all_live()
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
    """Return the one application-scoped port bound to the current V2 owner."""
    owner = getattr(app, "hass", None)
    existing = getattr(app, "execution_port", None)
    if isinstance(existing, ExecutionPort) and existing.v2_owner is owner:
        return existing
    port = ExecutionPort(owner)
    setattr(app, "execution_port", port)
    return port


__all__ = [
    "ControllerActionExecutionResult",
    "ExecutionPort",
    "ExecutionPortAudit",
    "ExecutionPortResult",
    "get_or_create_execution_port",
]
