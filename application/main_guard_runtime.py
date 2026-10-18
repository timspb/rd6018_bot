"""One-owner MAIN Guard reduction admission for an active EFB/Ca/Ca session.

Invoked only from the existing data_logger owner lock, never as a background
service. The *existing* ExecutionPort performs the Iset/OCP physical write;
the *existing* charge_session.json owner persists pending and ACK.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

from application.main_guard_transaction import MainGuardAuthority, MainGuardExecutionResult
from runtime.charge.strategy.main_guard_admission import MainGuardAdmission
from application.main_guard_checkpoint import CanonicalMainGuardCheckpoint
from runtime.charge.strategy.main_current_guard import PendingProposal
from runtime.charge.strategy.main_guard_shadow import MainGuardShadow


async def execute_due_main_guard(
    *, app: Any, port: Any, admission: MainGuardAdmission,
    shadow: MainGuardShadow, proposal: PendingProposal,
    session_path: str = "charge_session.json",
    clock: Callable[[], float] = time.monotonic,
) -> MainGuardExecutionResult | None:
    """Return None for missing authority; only a genuine accepted lease writes.

    No heartbeat/renew/arm or Output ON is issued here. Require *fresh Native
    ESPHome* source for the existing 900s EdgeSafetyLease. HA REST fallback
    cannot authorize this electrical change.
    """
    lock = getattr(port, "_guard_owner_lock", None)
    if (lock is None or getattr(lock, "owner_task", None) is not asyncio.current_task()
            or shadow.guard is None or shadow.guard.pending != proposal
            or (getattr(app, "charge_controller", None) is None)
            or not port.session_recovery_guard.may_run_automatic_control()):
        return None
    controller = app.charge_controller
    if (controller._v2_trace_session_id != admission.session_id
            or controller._v2_battery_id != admission.battery_id
            or controller.current_stage != controller.STAGE_MAIN
            or str(controller.battery_type).upper() not in ("EFB", "CA/CA")):
        return None
    mode = getattr(app, "rd_control_mode_manager", None)
    if getattr(mode, "hands_off", False):
        return None
    safety = getattr(app, "runtime_safety_guard", None)
    if safety is None or safety.edge_lease_enforced is not True:
        return None
    lease = getattr(safety, "edge_safety_lease", None)
    if lease is None or getattr(lease, "renewals_suspended", True):
        return None
    try:
        edge = await lease.read_state(require_native=True)
    except Exception:
        return None
    if (edge.armed is not True or edge.tripped is not False
            or edge.boot_quarantine is not False
            or edge.modbus_age_s < 0 or edge.modbus_age_s > 20
            or edge.remaining_s is None or edge.remaining_s < 60):
        return None

    writer = CanonicalMainGuardCheckpoint(
        controller=controller, owner_lock=lock, path=session_path,
        monotonic_now=clock,
    )
    result = await port.execute_main_current_guard_reduction(
        guard=shadow.guard, proposal=proposal,
        authority=MainGuardAuthority(
            session_id=admission.session_id, battery_id=admission.battery_id,
            segment_id=shadow.guard.segment_id,
            profile=str(controller.battery_type), stage="Main Charge",
            lease_armed=True, owner_authorized=True,
        ),
        persist=writer.persist, execution_lock=lock,
        now=clock, max_stage_current_a=12.0,
        ocp_offset_a=0.1, stabilize_delay_s=0.0,
    )
    if result is None:
        return None
    if result.verified:
        shadow.guard = result.guard
        shadow.proposal = None
        # Keep legacy periodic session saves aligned to the independently
        # acknowledged native Iset, not an old higher pre-ACK target.
        controller._device_set_current = result.guard.hardware_limit_a
        controller._phase_current_limit = result.guard.hardware_limit_a
    elif result.hardware_write_invoked or result.off_confirmed:
        # A physical write may have reached RD6018. Even if verified OFF
        # succeeded, do not let a subsequent automatic tick silently resume
        # the old session; the operator must explicitly clear quarantine.
        port.session_recovery_guard.quarantine(
            "main_guard_current_ocp_transaction_unconfirmed:" + result.reason
        )
    return result


__all__ = ["execute_due_main_guard"]
