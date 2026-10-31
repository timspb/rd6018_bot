"""MAIN Guard transactions through the existing ExecutionPort owner."""
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
    diagnostic: Mapping[str, Any] | None = None


class MainGuardExecutionFault(RuntimeError):
    def __init__(self, reason: str, *, diagnostic: Mapping[str, Any] | None = None):
        super().__init__(reason)
        self.diagnostic = diagnostic


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
            postflight_now = float(now())
            updated = guard.commit(
                proposal_id=proposal.proposal_id, now_s=postflight_now,
                measured_current_a=measured, measured_current_fresh=True,
                current_limit_readback_a=actual_i, current_readback_fresh=True,
                ocp_limit_a=actual_ocp, ocp_readback_fresh=True,
            )
            if updated.fault or updated.pending is not None:
                # Keep the pure guard as the acknowledgement authority, but do
                # not erase its specific fault at this application boundary.
                # Values below are limited to the three electrical readbacks
                # and monotonic proposal times; no credentials or payloads.
                fault = updated.fault or "proposal_still_pending"
                expected_ocp = float(proposal.target_limit_a) + EXPECTED_OCP_HEADROOM_A
                diagnostic = {
                    "guard_fault": fault,
                    "now_monotonic_s": postflight_now,
                    "proposal_created_monotonic_s": float(proposal.created_at_s),
                    "proposal_deadline_monotonic_s": float(proposal.deadline_s),
                    "measured_current_a": measured,
                    "iset_readback_a": actual_i,
                    "iset_target_a": float(proposal.target_limit_a),
                    "iset_delta_a": actual_i - float(proposal.target_limit_a),
                    "ocp_readback_a": actual_ocp,
                    "ocp_expected_a": expected_ocp,
                    "ocp_delta_a": actual_ocp - expected_ocp,
                    "readback_tolerance_a": READBACK_TOLERANCE_A,
                    "native_age_s": {
                        key: (after.get("_meta", {}).get(key, {}).get("age_s")
                              if isinstance(after.get("_meta"), Mapping)
                              and isinstance(after.get("_meta", {}).get(key), Mapping)
                              else None)
                        for key in _REQUIRED_NATIVE_KEYS
                    },
                    "native_evidence": {
                        key: {
                            field: after.get("_meta", {}).get(key, {}).get(field)
                            for field in ("source", "native_type", "subscription_timestamp_monotonic")
                        }
                        for key in _REQUIRED_NATIVE_KEYS
                        if isinstance(after.get("_meta"), Mapping)
                        and isinstance(after.get("_meta", {}).get(key), Mapping)
                    },
                }
                raise MainGuardExecutionFault(
                    f"postflight_guard_ack_rejected:{fault}", diagnostic=diagnostic
                )
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
                diagnostic=getattr(exc, "diagnostic", None),
            )


async def execute_main_guard_desulfation_return(
    port: Any, *, controller: Any, actions: Mapping[str, Any],
    execution_lock: asyncio.Lock, now: Now, max_stage_current_a: float,
    recipe_voltage_ceiling_v: float, has_ovp: bool, has_ocp: bool,
    ocp_offset_a: float, stabilize_delay_s: float,
    battery_v: float, current: float, ah: float,
) -> MainGuardExecutionResult:
    """Restore the existing guard's original MAIN current after verified OFF.

    This runs only on the existing recovery SAFE_WAIT -> MAIN execution path.
    It requires the controller's current guard and fresh direct ESP readback,
    commits the guard/session before re-enabling, and never writes a target if
    the preflight snapshot says Output is ON.
    """
    from runtime.charge.strategy.main_current_guard import EXPECTED_OCP_HEADROOM_A

    lock = getattr(port, "_guard_owner_lock", None)
    guard = getattr(controller, "_main_current_guard", None)
    if (not isinstance(execution_lock, asyncio.Lock) or lock is not execution_lock
            or getattr(lock, "owner_task", None) is not asyncio.current_task()):
        return MainGuardExecutionResult(guard, False, "canonical_execution_lock_required")
    if (guard is None or guard.fault or guard.pending
            or controller.current_stage != controller.STAGE_SAFE_WAIT
            or not isinstance(actions.get("verified_enable_transition"), Mapping)
            or actions["verified_enable_transition"].get("kind") != "recovery_safe_wait_to_main"):
        return MainGuardExecutionResult(guard, False, "recovery_guard_session_unavailable")
    continuation = getattr(controller, "_recovery_safe_wait", None)
    transition = actions["verified_enable_transition"]
    if (continuation is None or continuation.source_stage != controller.STAGE_DESULFATION
            or continuation.next_stage != controller.STAGE_MAIN
            or continuation.session_id != guard.session_id
            or transition.get("session_id") != guard.session_id):
        return MainGuardExecutionResult(guard, False, "desulfation_continuation_identity_mismatch")

    def fresh_native(live: Any) -> tuple[float, float, float] | None:
        if not isinstance(live, Mapping) or not _native_freshness(live):
            return None
        meta = live.get("_meta")
        for key in _REQUIRED_NATIVE_KEYS:
            item = meta.get(key) if isinstance(meta, Mapping) else None
            allowed_types = ({"SensorState", "BinarySensorState"}
                             if key == "protection_code" else {"SensorState"})
            if (not isinstance(item, Mapping) or item.get("source") != "esp_native_api"
                    or item.get("native_type") not in allowed_types):
                return None
        output = finite_float(live.get("output_state_code_v2"))
        measured_current = finite_float(live.get("current"))
        iset = canonical_programmed_readback(live, "set_current")
        ocp = canonical_programmed_readback(live, "ocp")
        if (output != 0 or measured_current is None or abs(measured_current) > READBACK_TOLERANCE_A
                or iset is None or ocp is None):
            return None
        protection = decode_protection_code(live.get("protection_code"))
        if protection.code is None or protection.unknown or protection.tripped:
            return None
        return iset, ocp, output

    hardware_write = False
    pre_return_guard = guard
    return_checkpoint_guard = None
    try:
        before = await port.execution_owner.get_all_live()
        before_values = fresh_native(before)
        if before_values is None:
            raise MainGuardExecutionFault("desulfation_return_preflight_stale_native")
        before_i, before_ocp, _ = before_values
        if (abs(before_i - guard.hardware_limit_a) > READBACK_TOLERANCE_A
                or abs(before_ocp - guard.hardware_limit_a - EXPECTED_OCP_HEADROOM_A)
                > READBACK_TOLERANCE_A):
            raise MainGuardExecutionFault("desulfation_return_preflight_guard_readback_mismatch")
        before_meta = before.get("_meta", {})
        before_stamps = [
            float(before_meta[k]["subscription_timestamp_monotonic"])
            for k in _REQUIRED_NATIVE_KEYS
        ]
        if not await port.request_verified_off():
            raise MainGuardExecutionFault("desulfation_return_verified_off_failed")
        off = await port.execution_owner.get_all_live()
        off_values = fresh_native(off)
        if off_values is None:
            raise MainGuardExecutionFault("desulfation_return_post_off_native_unavailable")
        off_i, off_ocp, _ = off_values
        off_meta = off.get("_meta", {})
        off_stamps = [float(off_meta[k]["subscription_timestamp_monotonic"])
                      for k in _REQUIRED_NATIVE_KEYS]
        if any(after <= prior for after, prior in zip(off_stamps, before_stamps)):
            raise MainGuardExecutionFault("desulfation_return_post_off_native_not_new")
        if (abs(off_i - guard.hardware_limit_a) > READBACK_TOLERANCE_A
                or abs(off_ocp - guard.hardware_limit_a - EXPECTED_OCP_HEADROOM_A)
                > READBACK_TOLERANCE_A):
            raise MainGuardExecutionFault("desulfation_return_post_off_guard_readback_mismatch")

        target_i = float(guard.initial_limit_a)
        target_v = float(actions["set_voltage"])
        target_ovp = float(actions["set_ovp"])
        target_ocp = target_i + EXPECTED_OCP_HEADROOM_A
        cap = float(max_stage_current_a)
        if (target_i > cap or target_i < HARDWARE_CURRENT_FLOOR_A
                or target_i > float(guard.recipe_initial_current_a)
                or target_v <= 0 or target_v > float(recipe_voltage_ceiling_v)
                or target_ocp > cap + EXPECTED_OCP_HEADROOM_A
                or float(ocp_offset_a) < EXPECTED_OCP_HEADROOM_A
                or (has_ovp and target_ovp <= target_v)
                or not has_ocp):
            raise MainGuardExecutionFault("desulfation_return_target_outside_existing_limits")
        hardware_write = True
        if has_ovp:
            if not await port.program_ovp(target_ovp):
                raise MainGuardExecutionFault("desulfation_return_ovp_setter_rejected")
        if not await port.program_voltage(target_v):
            raise MainGuardExecutionFault("desulfation_return_voltage_setter_rejected")
        # Output is proven OFF; program protection before restoring Iset.
        await port.apply_current_with_ocp(
            target_current_a=target_i, current_set_a=before_i,
            target_ocp_a=target_ocp, max_stage_current_a=cap,
            ocp_offset_a=float(ocp_offset_a), has_ocp=True,
            stabilize_delay_s=float(stabilize_delay_s),
        )
        readback = await port.execution_owner.get_all_live()
        values = fresh_native(readback)
        if values is None:
            raise MainGuardExecutionFault("desulfation_return_setpoint_readback_stale")
        actual_i, actual_ocp, _ = values
        readback_stamps = [float(readback["_meta"][k]["subscription_timestamp_monotonic"])
                           for k in _REQUIRED_NATIVE_KEYS]
        if any(after <= prior for after, prior in zip(readback_stamps, off_stamps)):
            raise MainGuardExecutionFault("desulfation_return_setpoint_readback_not_new")
        returned = guard.return_after_verified_desulfation(
            now_s=float(now()), from_stage="DESULFATION", to_stage="MAIN",
            output_off_proven=True, current_readback_a=actual_i,
            ocp_readback_a=actual_ocp, readbacks_fresh=True,
            segment_id=f"{guard.session_id}:MAIN:{float(now()).hex()}",
        )
        if returned.fault:
            raise MainGuardExecutionFault("desulfation_return_guard_rejected:" + returned.fault)
        return_checkpoint_guard = returned
        controller._main_current_guard = returned
        controller._device_set_current = actual_i
        controller._device_set_voltage = target_v
        old_revision = getattr(controller, "_main_current_guard_revision", None)
        controller._save_session(battery_v, current, ah)
        if controller._main_current_guard_revision == old_revision:
            raise MainGuardExecutionFault("desulfation_return_session_checkpoint_missing")

        enabled = await port.request_verified_on()
        if not enabled:
            raise MainGuardExecutionFault("desulfation_return_output_enable_failed")
        final = await port.execution_owner.verify_live_programming(
            voltage_v=target_v, current_a=target_i, ovp_v=target_ovp,
            ocp_a=target_ocp, recipe_voltage_ceiling_v=recipe_voltage_ceiling_v,
        )
        if not final:
            await port.request_verified_off()
            raise MainGuardExecutionFault("desulfation_return_final_readback_failed")
        return MainGuardExecutionResult(returned, True, "verified_desulfation_return_committed",
                                        hardware_write_invoked=True)
    except asyncio.CancelledError:
        if hardware_write:
            off_confirmed = await port.request_verified_off()
            if off_confirmed and return_checkpoint_guard is not None:
                await _compensate_interrupted_return(
                    port, controller,
                    pre_return_guard, return_checkpoint_guard,
                    battery_v, current, ah, now, max_stage_current_a,
                    ocp_offset_a, stabilize_delay_s,
                )
        raise
    except Exception as exc:
        off_confirmed = False
        if hardware_write:
            try:
                off_confirmed = bool(await port.request_verified_off())
            except Exception:
                pass
        if off_confirmed and return_checkpoint_guard is not None:
            try:
                await _compensate_interrupted_return(
                    port, controller, pre_return_guard, return_checkpoint_guard,
                    battery_v, current, ah, now, max_stage_current_a,
                    ocp_offset_a, stabilize_delay_s,
                )
                guard = controller._main_current_guard
            except Exception as compensation_error:
                # Keep the wider durable checkpoint in memory if compensation
                # cannot be proven; the next owner must reconcile it explicitly.
                logger = getattr(controller, "logger", None)
                if logger is not None:
                    logger.error("Could not compensate interrupted MAIN return: %s", compensation_error)
        return MainGuardExecutionResult(guard, False,
                                        type(exc).__name__ + ":" + str(exc),
                                        off_confirmed=off_confirmed,
                                        hardware_write_invoked=hardware_write)


async def _compensate_interrupted_return(
    port: Any, controller: Any, prior: MainCurrentGuard,
    checkpoint: MainCurrentGuard, battery_v: float, current: float,
    ah: float, now: Now, max_stage_current_a: float, ocp_offset_a: float,
    stabilize_delay_s: float,
) -> None:
    """Durably retain the interrupted epoch while restoring its old Iset cap.

    The safe-wait stage and segment identity remain durable. This makes retry
    possible after restart without claiming MAIN progress or authorizing the
    raised ceiling that was checkpointed before Output ON.
    """
    from dataclasses import replace
    before = await port.execution_owner.get_all_live()
    values = None
    before_meta = before.get("_meta", {}) if isinstance(before, Mapping) else {}
    before_stamps = {}
    if isinstance(before, Mapping) and _native_freshness(before):
        if all(isinstance(before_meta.get(key), Mapping)
               and before_meta[key].get("source") == "esp_native_api"
               and before_meta[key].get("native_type") in (
                   {"SensorState", "BinarySensorState"} if key == "protection_code"
                   else {"SensorState"}) for key in _REQUIRED_NATIVE_KEYS):
            before_stamps = {
                key: float(before_meta[key]["subscription_timestamp_monotonic"])
                for key in _REQUIRED_NATIVE_KEYS
            }
            output = finite_float(before.get("output_state_code_v2"))
            set_i = canonical_programmed_readback(before, "set_current")
            set_ocp = canonical_programmed_readback(before, "ocp")
            actual_i = finite_float(before.get("current"))
            protection = decode_protection_code(before.get("protection_code"))
            if (output == 0 and set_i is not None and set_ocp is not None
                    and actual_i is not None and abs(actual_i) <= READBACK_TOLERANCE_A
                    and not protection.unknown and not protection.tripped):
                values = (set_i, set_ocp)
    if values is None:
        raise MainGuardExecutionFault("interrupted_return_compensation_native_readback_unavailable")
    target_ocp = prior.hardware_limit_a + EXPECTED_OCP_HEADROOM_A
    if (prior.hardware_limit_a > max_stage_current_a
            or ocp_offset_a < EXPECTED_OCP_HEADROOM_A):
        raise MainGuardExecutionFault("interrupted_return_compensation_outside_envelope")
    await port.apply_current_with_ocp(
        target_current_a=prior.hardware_limit_a, current_set_a=values[0],
        target_ocp_a=target_ocp, max_stage_current_a=max_stage_current_a,
        ocp_offset_a=ocp_offset_a, has_ocp=True,
        stabilize_delay_s=stabilize_delay_s,
    )
    after = await port.execution_owner.get_all_live()
    if not isinstance(after, Mapping) or not _native_freshness(after):
        raise MainGuardExecutionFault("interrupted_return_compensation_readback_stale")
    after_meta = after.get("_meta", {})
    after_i = canonical_programmed_readback(after, "set_current")
    after_ocp = canonical_programmed_readback(after, "ocp")
    after_stamps = {}
    if all(isinstance(after_meta.get(key), Mapping)
           and after_meta[key].get("source") == "esp_native_api"
           and after_meta[key].get("native_type") in (
               {"SensorState", "BinarySensorState"} if key == "protection_code"
               else {"SensorState"}) for key in _REQUIRED_NATIVE_KEYS):
        after_stamps = {
            key: float(after_meta[key]["subscription_timestamp_monotonic"])
            for key in _REQUIRED_NATIVE_KEYS
        }
    measured_after = finite_float(after.get("current"))
    if (finite_float(after.get("output_state_code_v2")) != 0
            or measured_after is None or abs(measured_after) > READBACK_TOLERANCE_A
            or after_i is None or after_ocp is None
            or abs(after_i - prior.hardware_limit_a) > READBACK_TOLERANCE_A
            or abs(after_ocp - target_ocp) > READBACK_TOLERANCE_A
            or not after_stamps
            or any(after_stamps[key] <= before_stamps[key]
                   for key in _REQUIRED_NATIVE_KEYS)):
        raise MainGuardExecutionFault("interrupted_return_compensation_readback_mismatch")
    compensated = replace(
        prior, segment_id=checkpoint.segment_id,
        hardware_limit_a=prior.hardware_limit_a,
        accrued_output_on_s=0.0, last_observed_at_s=float(now()),
        last_output_on=False, last_stage_main=True,
    )
    old_guard = getattr(controller, "_main_current_guard", None)
    old_device_current = getattr(controller, "_device_set_current", None)
    old_revision = getattr(controller, "_main_current_guard_revision", None)
    controller._main_current_guard = compensated
    controller._device_set_current = compensated.hardware_limit_a
    try:
        controller._save_session(battery_v, current, ah)
        if controller._main_current_guard_revision == old_revision:
            raise MainGuardExecutionFault("interrupted_return_compensation_not_durable")
    except BaseException:
        controller._main_current_guard = checkpoint
        controller._device_set_current = old_device_current
        raise


__all__ = [
    "MainGuardAuthority", "MainGuardExecutionFault", "MainGuardExecutionResult",
    "MAX_READBACK_AGE_S", "execute_main_guard_reduction",
    "execute_main_guard_desulfation_return",
]