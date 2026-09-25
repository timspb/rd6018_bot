"""Single application boundary for physical actions owned by V2.

The port deliberately contains no phase, program, or target-selection logic.
It accepts an already-created :class:`ExecutionIntent`, delegates to the
existing V2 owner, verifies readback, and records the correlation envelope.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Any

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

    async def disable(self, intent: ExecutionIntent, *, identity: Any = None, reason: str = "requested_disable") -> ExecutionPortResult:
        # Verified OFF remains available for legacy/containment paths without
        # inventing a lifecycle identity. The audit explicitly records that gap.
        try:
            accepted = bool(await self.v2_owner.turn_off())
            live = await self.v2_owner.get_all_live()
            output_off = str(live.get("switch", "")).lower() in {"off", "false", "0"}
            verified = accepted and output_off
            return self._result(intent, identity, "disable", accepted, verified, reason if verified else "off_verification_failed")
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            return self._result(intent, identity, "disable", False, False, type(exc).__name__)

    @staticmethod
    def _identity_valid(identity: Any) -> bool:
        return bool(identity is not None and getattr(identity, "session_id", "") and getattr(identity, "trace_id", ""))

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


__all__ = ["ExecutionPort", "ExecutionPortAudit", "ExecutionPortResult"]
