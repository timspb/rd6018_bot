"""Opt-in MAIN Guard transaction through existing ExecutionPort owner.

Not called by production. Fail-closed transaction for future controller
integration, NOT authorization to energize RD6018; no voltage/current increase.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
import math
from typing import Any, Awaitable, Callable, Mapping

from rd6018_telemetry import canonical_programmed_readback, finite_float
from runtime.charge.strategy.main_current_guard import (
    EXPECTED_OCP_HEADROOM_A, HARDWARE_CURRENT_FLOOR_A,
    READBACK_TOLERANCE_A, MainCurrentGuard, PendingProposal,
)

SaveSnapshot = Callable[[dict[str, Any]], Awaitable[None]]
Now = Callable[[], float]
MAX_READBACK_AGE_S = 10.0


@dataclass(frozen=True)
class MainGuardAuthority:
    session_id: str
    battery_id: str
    segment_id: str
    profile: str
    stage: str
    lease_armed: bool
    owner_authorized: bool


@dataclass(frozen=True)
class MainGuardExecutionResult:
    guard: MainCurrentGuard
    verified: bool
    reason: str
    off_confirmed: bool = False


class MainGuardExecutionFault(RuntimeError):
    pass


def _fresh(live: Mapping[str, Any], name: str) -> bool:
    meta = live.get("_meta")
    if not isinstance(meta, Mapping):
        return False
    item = meta.get(name)
    if not isinstance(item, Mapping) or item.get("status") != "ok":
        return False
    age = finite_float(item.get("age_s"))
    return age is not None and 0 <= age <= MAX_READBACK_AGE_S


def _positive_on_snapshot(live: Mapping[str, Any]) -> tuple[float, float, float]:
    """Require canonical Output ON, protection clear, and hardware readbacks."""
    for name in (
        "output_state_code_v2", "current", "set_current_readback_v2",
        "ocp_readback_v2", "protection_code",
    ):
        if not _fresh(live, name):
            raise MainGuardExecutionFault("stale_or_missing_" + name)
    output = finite_float(live.get("output_state_code_v2"))
    protect = finite_float(live.get("protection_code"))
    actual_i = finite_float(live.get("current"))
    programmed_i = canonical_programmed_readback(live, "set_current")
    programmed_ocp = canonical_programmed_readback(live, "ocp")
    if output != 1 or protect != 0:
        raise MainGuardExecutionFault("output_not_proven_on_or_protection_fault")
    if actual_i is None or actual_i < 0 or programmed_i is None or programmed_ocp is None:
        raise MainGuardExecutionFault("canonical_readback_unavailable")
    return actual_i, programmed_i, programmed_ocp


async def execute_main_guard_reduction(
    port: Any, *,
    guard: MainCurrentGuard,
    proposal: PendingProposal,
    authority: MainGuardAuthority,
    persist: SaveSnapshot,
    execution_lock: asyncio.Lock,
    now: Now,
    max_stage_current_a: float,
    ocp_offset_a: float,
    stabilize_delay_s: float,
) -> MainGuardExecutionResult:
    """Execute only a decrease, using existing protected current/OCP order.

    Persist callback must be the canonical session owner's atomic durable
    checkpoint writer, with a shared lifecycle/execution lock. Without this
    integration the boundary must NOT be connected to production.

    All failures request verified OFF; failed OFF is never reported as success.
    """
    if not isinstance(execution_lock, asyncio.Lock):
        raise TypeError("shared owner execution lock required")
    async with execution_lock:
        try:
            if (
                authority.session_id != guard.session_id
                or authority.battery_id != guard.battery_id
                or authority.segment_id != guard.segment_id
                or str(authority.profile).upper() not in ("EFB", "CA/CA")
                or authority.stage != "Main Charge"
                or authority.lease_armed is not True
                or authority.owner_authorized is not True
            ):
                raise MainGuardExecutionFault("main_session_owner_lease_unproven")
            if (
                guard.fault or guard.pending != proposal
                or not guard.session_id or not guard.battery_id
                or not guard.segment_id or proposal is None
            ):
                raise MainGuardExecutionFault("invalid_or_unbound_pending_proposal")
            cap = finite_float(max_stage_current_a)
            margin = finite_float(ocp_offset_a)
            if cap is None or margin is None or cap <= 0 or margin < EXPECTED_OCP_HEADROOM_A:
                raise MainGuardExecutionFault("invalid_current_ocp_envelope")
            current_target = float(proposal.target_limit_a)
            ocp_target = current_target + EXPECTED_OCP_HEADROOM_A
            if (
                not math.isfinite(current_target)
                or current_target < HARDWARE_CURRENT_FLOOR_A
                or current_target >= guard.hardware_limit_a
                or current_target > guard.initial_limit_a
                or current_target > cap
                or ocp_target > cap + margin
            ):
                raise MainGuardExecutionFault("current_reduction_not_within_envelope")
            ts = float(now())
            if not math.isfinite(ts) or ts < proposal.created_at_s or ts > proposal.deadline_s:
                raise MainGuardExecutionFault("proposal_expired")
            before = await port.execution_owner.get_all_live()
            if not isinstance(before, Mapping):
                raise MainGuardExecutionFault("preflight_unavailable")
            _, previous_i, previous_ocp = _positive_on_snapshot(before)
            if abs(previous_i - guard.hardware_limit_a) > READBACK_TOLERANCE_A:
                raise MainGuardExecutionFault("preflight_current_ceiling_disagrees_with_journal")
            if abs(previous_ocp - previous_i - EXPECTED_OCP_HEADROOM_A) > READBACK_TOLERANCE_A:
                raise MainGuardExecutionFault("preflight_ocp_disagrees_with_journal")
            await persist(guard.snapshot())  # durable pending before hardware
            await port.apply_current_with_ocp(
                target_current_a=current_target,
                current_set_a=previous_i,
                target_ocp_a=ocp_target,
                max_stage_current_a=cap,
                ocp_offset_a=margin,
                has_ocp=True,
                stabilize_delay_s=stabilize_delay_s,
            )
            after = await port.execution_owner.get_all_live()
            if not isinstance(after, Mapping):
                raise MainGuardExecutionFault("postflight_unavailable")
            measured, actual_i, actual_ocp = _positive_on_snapshot(after)
            updated = guard.commit(
                proposal_id=proposal.proposal_id, now_s=float(now()),
                measured_current_a=measured, measured_current_fresh=True,
                current_limit_readback_a=actual_i, current_readback_fresh=True,
                ocp_limit_a=actual_ocp, ocp_readback_fresh=True,
            )
            if updated.fault or updated.pending is not None:
                raise MainGuardExecutionFault("postflight_guard_ack_rejected")
            await persist(updated.snapshot())  # post-ACK durable commit
            return MainGuardExecutionResult(updated, True, "readback_and_journal_verified")
        except asyncio.CancelledError:
            await port.request_verified_off()
            raise
        except Exception as exc:
            off_confirmed = False
            try:
                off_confirmed = bool(await port.request_verified_off())
            except Exception:
                pass
            return MainGuardExecutionResult(
                guard, False, type(exc).__name__ + ":" + str(exc),
                off_confirmed=off_confirmed,
            )


__all__ = [
    "MainGuardAuthority", "MainGuardExecutionFault", "MainGuardExecutionResult",
    "MAX_READBACK_AGE_S", "execute_main_guard_reduction",
]
