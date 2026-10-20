"""Production startup recovery coordinator.

This is an orchestration boundary only. The composed application remains the
owner of controller/session/safety/physical semantics; this module preserves the
existing recovery order and delegates to those owners.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from functools import wraps
import time
from typing import Any

from application.execution_port import get_or_create_execution_port
from diagnostic_persistence import recover_diagnostic_persistence
from runtime.charge.persistence import SESSION_FILE
from runtime.charge.strategy.main_guard_pre_on import assess_main_guard_before_output_on
from runtime.charge.strategy.main_guard_session import GuardJournalError, read_guard
from runtime.charge.strategy.main_guard_admission import read_canonical_session
from rd6018_telemetry import as_bool


def _serialized_deferred_restore(operation):
    """Protect restore state and normal physical reenable as one owner action."""
    @wraps(operation)
    async def wrapped(self):
        port = get_or_create_execution_port(self.app)
        lock = port._guard_owner_lock
        if lock is None:
            raise RuntimeError("deferred restore lacks canonical execution owner")
        async with lock:
            return await operation(self)
    return wrapped


class StartupRecovery:
    def __init__(self, app: Any, managed_mix: Any, managed_live: Any, live_observer: Any = None) -> None:
        self.app = app
        self.managed_mix = managed_mix
        self.managed_live = managed_live
        self.live_observer = live_observer
        self.last_guard_assessment = None

    async def recover_managed_startup_authority(self) -> bool:
        if not get_or_create_execution_port(self.app).session_recovery_guard.may_run_automatic_control():
            return False
        if not await self.managed_mix.recover_startup():
            return False
        if not await self.managed_live.recover_startup():
            return False
        if self.live_observer is not None and not await self.live_observer.recover_startup():
            return False
        await recover_diagnostic_persistence(self.app)
        return True

    @_serialized_deferred_restore
    async def replay_deferred_startup_restore(self) -> None:
        """Replay deferred managed restore through the canonical safe owner."""
        app = self.app
        execution_port = get_or_create_execution_port(app)
        if not execution_port.session_recovery_guard.may_run_automatic_control():
            return
        controller = app.charge_controller
        candidate = getattr(controller, "_guarded_restore_candidate", None)
        if candidate is not None:
            # This is evidence collection only. Even RECONCILED never admits
            # controller state or enters the Output-ON path in this sprint.
            from runtime.charge.strategy.main_guard_pre_on import GuardPreOnAssessment

            def record_assessment(assessment):
                self.last_guard_assessment = assessment
                if assessment.status == "BLOCKED":
                    controller._guarded_restore_candidate = replace(
                        candidate, blocker=assessment.reason,
                    )

            lock = execution_port._guard_owner_lock
            if (lock is None or getattr(lock, "owner_task", None) is not asyncio.current_task()):
                record_assessment(GuardPreOnAssessment(
                    "BLOCKED", "execution_owner_or_lease_unproven",
                ))
                return
            native_reader = getattr(app.hass, "get_native_guard_pre_on_snapshot", None)
            if not callable(native_reader):
                record_assessment(GuardPreOnAssessment(
                    "BLOCKED", "direct_native_snapshot_api_unavailable",
                ))
                return
            native_live = await native_reader()
            if native_live is None:
                record_assessment(GuardPreOnAssessment(
                    "BLOCKED", "direct_native_callback_evidence_unavailable",
                ))
                return
            canonical = read_canonical_session(SESSION_FILE)
            if not isinstance(canonical, dict):
                record_assessment(GuardPreOnAssessment(
                    "BLOCKED", "canonical_document_unavailable",
                ))
                return
            try:
                now = time.time()
                restored_guard, candidate_revision = read_guard(
                    dict(candidate.document), session_id=candidate.session_id or "",
                    battery_id=candidate.battery_id or "", now_s=now,
                )
                _canonical_guard, canonical_revision = read_guard(
                    canonical, session_id=candidate.session_id or "",
                    battery_id=candidate.battery_id or "", now_s=now,
                )
            except (GuardJournalError, ValueError, TypeError, OverflowError) as exc:
                record_assessment(GuardPreOnAssessment(
                    "BLOCKED", "canonical_guard_untrustworthy:" + type(exc).__name__,
                ))
                return
            if (candidate_revision != candidate.guard_revision
                    or canonical_revision != candidate_revision
                    or canonical.get("v2_trace_session_id") != candidate.session_id
                    or canonical.get("v2_battery_id") != candidate.battery_id):
                record_assessment(GuardPreOnAssessment(
                    "BLOCKED", "canonical_document_identity_or_revision_changed",
                ))
                return
            lease_meta = native_live.get("_lease_meta")
            lease = as_bool(native_live.get("edge_lease_armed"))
            try:
                lease_age = float(lease_meta.get("age_s")) if isinstance(lease_meta, dict) else -1
            except (TypeError, ValueError, OverflowError):
                lease_age = -1
            lease_fresh = (
                isinstance(lease_meta, dict)
                and lease_meta.get("source") == "esp_native_api"
                and lease_meta.get("status") == "ok"
                and lease_meta.get("native_type") == "BinarySensorState"
                and 0 <= lease_age <= 10.0
            )
            assessment = assess_main_guard_before_output_on(
                session_document=canonical,
                restored_guard=restored_guard,
                native_live=native_live,
                session_id=candidate.session_id or "",
                battery_id=candidate.battery_id or "",
                profile=str(canonical.get("profile") or ""),
                stage=str(canonical.get("stage") or ""),
                target_current_a=restored_guard.hardware_limit_a,
                owner_authorized=True,
                edge_lease_armed=lease_fresh and lease is True,
                now_epoch_s=now,
            )
            latest = read_canonical_session(SESSION_FILE)
            try:
                if not isinstance(latest, dict):
                    raise GuardJournalError("canonical_document_unavailable")
                _latest_guard, latest_revision = read_guard(
                    latest, session_id=candidate.session_id or "",
                    battery_id=candidate.battery_id or "", now_s=time.time(),
                )
            except (GuardJournalError, ValueError, TypeError, OverflowError) as exc:
                record_assessment(GuardPreOnAssessment(
                    "BLOCKED", "canonical_document_recheck_failed:" + type(exc).__name__,
                ))
                return
            if (latest_revision != canonical_revision
                    or latest.get("v2_trace_session_id") != candidate.session_id
                    or latest.get("v2_battery_id") != candidate.battery_id):
                record_assessment(GuardPreOnAssessment(
                    "BLOCKED", "canonical_document_identity_or_revision_changed",
                ))
                return
            record_assessment(assessment)
            # Deliberately return regardless of assessment: no activation is
            # installed, and the persisted bytes/candidate remain quarantined.
            return
        live = await app.hass.get_all_live()

        if not bool(getattr(controller, "is_active", False)):
            ok, _msg = controller.try_restore_session(
                app._safe_float(live.get("battery_voltage")),
                app._safe_float(live.get("current")),
                app._safe_float(live.get("ah")),
                output_is_on=(str(live.get("switch", "")).lower() == "on"),
                is_cv=str(live.get("is_cv", "")).lower() == "on",
                is_cc=str(live.get("is_cc", "")).lower() == "on",
            )
            if not ok:
                return
            app._apply_restore_time_corrections(controller, live)
            app.last_checkpoint_time = app.time.time()
            app.logger.info(
                "Deferred startup session state restored after MANAGED authority reconciliation: %s",
                controller.current_stage,
            )

        if app._operator_pause_active():
            app.logger.info("Deferred startup auto-resume skipped: operator pause is active")
            return
        if not app._restore_allows_auto_enable(controller):
            return

        output_state = str(live.get("switch", "")).strip().lower()
        safe_wait_stage = getattr(controller, "STAGE_SAFE_WAIT", None)
        if safe_wait_stage is not None and controller.current_stage == safe_wait_stage:
            if output_state == "off":
                return
            if output_state != "on":
                raise RuntimeError("deferred startup restore cannot resolve SAFE_WAIT Output state")
            confirmed_off = await execution_port.request_verified_off()
            if not confirmed_off:
                raise RuntimeError("deferred startup SAFE_WAIT Output OFF was not confirmed")
            return

        if output_state == "on":
            return
        if output_state != "off":
            raise RuntimeError("deferred startup restore cannot resolve canonical Output state")

        raw_temp = live.get("temp_ext")
        if raw_temp is None or str(raw_temp).strip().lower() in {"", "unknown", "unavailable", "none"}:
            raise RuntimeError("deferred startup restore requires fresh battery temperature")
        temp_ext = app._safe_float(raw_temp)
        uv, ui = controller._get_target_v_i(temp_ext)
        await app._apply_phase_protection(uv, ui)
        await execution_port.program_voltage(uv)
        await execution_port.program_current(app._cap_current(ui))
        enabled = await execution_port.request_verified_on()
        if not enabled:
            raise RuntimeError("deferred startup safe Output enable was not confirmed")
        app.logger.info(
            "Deferred startup session physically resumed after MANAGED authority reconciliation: %s",
            controller.current_stage,
        )
