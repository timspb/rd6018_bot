"""Opt-in MAIN Guard transaction through existing ExecutionPort owner.

Not called by production. Fail-closed transaction for future controller
integration, NOT authorization to energize RD6018; no voltage/current increase.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
import math
from typing import Any, Awaitable, Callable, Mapping

from rd6018_telemetry import (
    canonical_programmed_readback, decode_protection_code, finite_float,
    telemetry_freshness,
)
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
    hardware_write_invoked: bool = False


class MainGuardExecutionFault(RuntimeError):
    pass


class _ConfirmedPrewriteFault(MainGuardExecutionFault):
    """Fresh native evidence proves an active fault requiring containment."""


_REQUIRED_NATIVE_KEYS = (
    "output_state_code_v2", "current", "set_current_readback_v2",
    "ocp_readback_v2", "protection_code",
)


def _native_freshness(live: Mapping[str, Any]) -> bool:
    # Unlike the generic compatibility function, Guard MUST have source
    # metadata. Use real HA last_reported/last_updated or verified age_s,
    # and bound skew across all 5 independent native observations.
    meta = live.get("_meta")
    if not isinstance(meta, Mapping):
        return False
    return telemetry_freshness(
        live, _REQUIRED_NATIVE_KEYS,
        max_age_s=MAX_READBACK_AGE_S, max_skew_s=MAX_READBACK_AGE_S,
    ).valid


def _positive_on_snapshot(live: Mapping[str, Any]) -> tuple[float, float, float]:
    """Require canonical Output ON, protection clear, and hardware readbacks."""
    if not _native_freshness(live):
        raise MainGuardExecutionFault("stale_or_skewed_native_evidence")
    output = finite_float(live.get("output_state_code_v2"))
    protection = decode_protection_code(live.get("protection_code"))
    actual_i = finite_float(live.get("current"))
    programmed_i = canonical_programmed_readback(live, "set_current")
    programmed_ocp = canonical_programmed_readback(live, "ocp")
    if output != 1:
        raise MainGuardExecutionFault("output_not_proven_on")
    if protection.code is None or protection.unknown:
        raise MainGuardExecutionFault("protection_code_unavailable_or_unknown")
    if protection.tripped:
        raise _ConfirmedPrewriteFault("confirmed_native_protection_trip")
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

    Preflight and durable-pending failures are DENY decisions and stay read-only.
    Once a hardware setter has been invoked, a failure is physically ambiguous
    and requests verified OFF; failed OFF is never reported as success.
    """
    # Never accept a random lock: it could only serialize this one Guard call,
    # while the real controller, manual commands and startup race around it.
    bound_lock = getattr(port, "_guard_owner_lock", None)
    if (not isinstance(execution_lock, asyncio.Lock)
            or bound_lock is None or execution_lock is not bound_lock):
        raise TypeError("canonical owner lifecycle lock is not bound")
    async with execution_lock:
        hardware_write_invoked = False
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
            if previous_i > guard.hardware_limit_a + READBACK_TOLERANCE_A:
                raise _ConfirmedPrewriteFault("preflight_current_above_persisted_guard")
            expected_ocp = guard.hardware_limit_a + EXPECTED_OCP_HEADROOM_A
            if previous_ocp > expected_ocp + READBACK_TOLERANCE_A:
                raise _ConfirmedPrewriteFault("preflight_ocp_above_persisted_guard")
            if abs(previous_i - guard.hardware_limit_a) > READBACK_TOLERANCE_A:
                raise MainGuardExecutionFault("preflight_current_ceiling_disagrees_with_journal")
            if abs(previous_ocp - previous_i - EXPECTED_OCP_HEADROOM_A) > READBACK_TOLERANCE_A:
                raise MainGuardExecutionFault("preflight_ocp_disagrees_with_journal")
            await persist(guard.snapshot())  # durable pending before hardware
            # From this point a setter may have reached the RD even if its call
            # raises or returns an uncertain result. Only this ambiguity enters
            # physical containment; stale/preflight uncertainty remains DENY.
            hardware_write_invoked = True
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
            return MainGuardExecutionResult(updated, True, "readback_and_journal_verified", hardware_write_invoked=True)
        except asyncio.CancelledError:
            if hardware_write_invoked:
                await port.request_verified_off()
            raise
        except _ConfirmedPrewriteFault as exc:
            try:
                off_confirmed = bool(await port.request_verified_off())
            except Exception:
                off_confirmed = False
            return MainGuardExecutionResult(
                guard, False, type(exc).__name__ + ":" + str(exc),
                off_confirmed=off_confirmed,
            )
        except Exception as exc:
            off_confirmed = False
            if hardware_write_invoked:
                try:
                    off_confirmed = bool(await port.request_verified_off())
                except Exception:
                    pass
            return MainGuardExecutionResult(
                guard, False, type(exc).__name__ + ":" + str(exc),
                off_confirmed=off_confirmed,
                hardware_write_invoked=hardware_write_invoked,
            )


__all__ = [
    "MainGuardAuthority", "MainGuardExecutionFault", "MainGuardExecutionResult",
    "MAX_READBACK_AGE_S", "execute_main_guard_reduction",
]
