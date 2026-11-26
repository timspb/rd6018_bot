"""Production startup recovery coordinator.

This is an orchestration boundary only. The composed application remains the
owner of controller/session/safety/physical semantics; this module preserves the
existing recovery order and delegates to those owners.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from functools import wraps
import hashlib
import json
import logging
from pathlib import Path
import time
from typing import Any

logger = logging.getLogger("rd6018.startup_recovery")

from application.execution_port import get_or_create_execution_port
from diagnostic_persistence import recover_diagnostic_persistence
from runtime.charge.persistence import (
    SESSION_FILE, StartPendingAction, StartPendingStatus,
    finish_start_pending, read_canonical_session, read_start_pending,
)
from runtime.charge.controller_state import clear_link_lost_timestamp
from runtime.charge.link_session_recovery import (
    RecoveryAction,
    RecoveryAuthorizationInput,
    RecoveryRoute,
    authorize_recovery_action,
)
from runtime.charge.strategy.main_guard_pre_on import assess_main_guard_before_output_on
from runtime.charge.strategy.main_guard_session import GuardJournalError, read_guard
from runtime.charge.session import (
    _issue_guarded_restore_activation_permit,
    issue_guarded_physical_resume_permit,
)
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
            try:
                return await operation(self)
            except asyncio.CancelledError:
                port.session_recovery_guard.quarantine("deferred_restore_cancelled")
                raise
            except Exception as exc:
                # A failed deferred restore may have loaded or partly applied
                # its candidate before the failure. Keep later automatic
                # control blocked even if an outer startup owner handles it.
                port.session_recovery_guard.quarantine(
                    "deferred_restore_failed:" + type(exc).__name__
                )
                raise
    return wrapped


class StartupRecovery:
    def __init__(self, app: Any, managed_mix: Any, managed_live: Any, live_observer: Any = None) -> None:
        self.app = app
        self.managed_mix = managed_mix
        self.managed_live = managed_live
        self.live_observer = live_observer
        self.last_guard_assessment = None

    async def recover_managed_startup_authority(self) -> bool:
        if not await self._settle_start_pending_before_restore():
            return False
        if not get_or_create_execution_port(self.app).session_recovery_guard.may_run_automatic_control():
            logger.warning("Managed startup recovery blocked: session recovery guard")
            return False
        if not await self.managed_mix.recover_startup():
            logger.warning("Managed startup recovery blocked: managed_mix")
            return False
        if not await self.managed_live.recover_startup():
            logger.warning("Managed startup recovery blocked: managed_live")
            return False
        if self.live_observer is not None and not await self.live_observer.recover_startup():
            logger.warning("Managed startup recovery blocked: live_observer")
            return False
        await recover_diagnostic_persistence(self.app)
        logger.info("Managed startup recovery completed")
        return True

    async def _settle_start_pending_before_restore(self) -> bool:
        """Require this process to prove OFF before restoring embedded prior bytes."""
        raw, pending, error = read_start_pending(SESSION_FILE)
        if error:
            get_or_create_execution_port(self.app).session_recovery_guard.quarantine(
                "start_pending_unreadable:" + error
            )
            return False
        if raw is not None:
            try:
                raw_document = json.loads(raw.decode("utf-8"))
            except (UnicodeError, ValueError):
                raw_document = None
            if (isinstance(raw_document, dict)
                    and any(str(key).startswith("start_transaction_")
                            and key not in {"start_transaction_generation", "start_transaction_pending_v1"}
                            for key in raw_document)):
                get_or_create_execution_port(self.app).session_recovery_guard.quarantine(
                    "start_pending_unknown_transaction_envelope"
                )
                return False
            if (isinstance(raw_document, dict)
                    and "start_transaction_pending_v1" in raw_document
                    and pending is None):
                get_or_create_execution_port(self.app).session_recovery_guard.quarantine(
                    "start_pending_marker_without_valid_envelope"
                )
                return False
        if pending is None:
            return True
        port = get_or_create_execution_port(self.app)
        try:
            receipt = await port.request_emergency_off_receipt()
            if (receipt is None or receipt.requested_target is not False
                    or receipt.terminal_status != "APPLIED"
                    or type(receipt.observed_r18) is not int or receipt.observed_r18 != 0
                    or not isinstance(receipt.terminal_completed_monotonic, (int, float))
                    or isinstance(receipt.terminal_completed_monotonic, bool)
                    or type(receipt.connection_generation) is not int):
                raise RuntimeError("start_pending_off_receipt_unproven")
            report = await self.app.hass.get_native_physical_output_report()
            if not isinstance(report, tuple) or len(report) != 2:
                raise RuntimeError("start_pending_native_output_report_missing")
            value, meta = report
            timestamp = meta.get("subscription_timestamp_monotonic") if isinstance(meta, dict) else None
            if (type(value) is bool or value != 0
                    or not isinstance(meta, dict) or meta.get("status") != "ok"
                    or meta.get("native_type") != "SensorState"
                    or type(meta.get("connection_generation")) is not int
                    or meta["connection_generation"] != receipt.connection_generation
                    or not isinstance(timestamp, (int, float)) or isinstance(timestamp, bool)
                    or timestamp <= receipt.terminal_completed_monotonic):
                raise RuntimeError("start_pending_post_receipt_native_off_unproven")
            result = finish_start_pending(
                raw, pending, action=StartPendingAction.ROLLBACK, path=SESSION_FILE,
            )
            if result.status is not StartPendingStatus.COMMITTED:
                raise RuntimeError("start_pending_exact_rollback_unproven")
            observed, after_pending, after_error = read_start_pending(SESSION_FILE)
            expected = (pending.get("previous_raw_utf8", "").encode("utf-8")
                        if pending.get("previous_exists") else None)
            if after_error or after_pending is not None or observed != expected:
                raise RuntimeError("start_pending_rollback_readback_mismatch")
            return True
        except Exception as exc:
            try:
                port.session_recovery_guard.quarantine(
                    "start_pending_recovery:" + type(exc).__name__
                )
            except Exception:
                pass
            logger.error("START_PENDING recovery quarantined: %s", type(exc).__name__)
            return False

    @_serialized_deferred_restore
    async def replay_deferred_startup_restore(self) -> None:
        """Replay deferred managed restore through the canonical safe owner."""
        app = self.app
        execution_port = get_or_create_execution_port(app)
        if execution_port.guarded_restore_activated_off:
            # A restored software session cannot reuse startup auto-resume.
            # A future explicit physical-resume transaction must clear this
            # latch only after a new locked Native pre-ON assessment.
            return
        if not execution_port.session_recovery_guard.may_run_automatic_control():
            return
        controller = app.charge_controller
        candidate = getattr(controller, "_guarded_restore_candidate", None)
        if candidate is not None:
            # Guarded activation is one lock-bound restore transaction. It
            # admits software state only; the shared port remains latched
            # against every ordinary ON path pending a separate resume owner.
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
            if getattr(controller, "_guarded_restore_candidate", None) is not candidate:
                record_assessment(GuardPreOnAssessment(
                    "BLOCKED", "guarded_restore_candidate_replaced_during_assessment",
                ))
                return
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
            saved_at = canonical.get("saved_at")
            if (isinstance(saved_at, bool) or not isinstance(saved_at, (int, float))
                    or not 0 <= time.time() - float(saved_at) <= 3600.0
                    or canonical.get("state") == "retired"):
                record_assessment(GuardPreOnAssessment(
                    "BLOCKED", "canonical_document_stale_or_retired",
                ))
                return
            if candidate.canonical_bytes_sha256 is not None:
                try:
                    candidate_bytes_match = (
                        hashlib.sha256(Path(SESSION_FILE).read_bytes()).hexdigest()
                        == candidate.canonical_bytes_sha256
                    )
                except OSError:
                    candidate_bytes_match = False
                if not candidate_bytes_match:
                    record_assessment(GuardPreOnAssessment(
                        "BLOCKED", "canonical_file_bytes_changed",
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
            if dict(candidate.document) != canonical:
                record_assessment(GuardPreOnAssessment(
                    "BLOCKED", "candidate_document_differs_from_canonical",
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
            try:
                target_current = float(canonical.get("target_current"))
            except (TypeError, ValueError, OverflowError):
                record_assessment(GuardPreOnAssessment(
                    "BLOCKED", "persisted_resume_target_unavailable",
                ))
                return
            if isinstance(canonical.get("target_current"), bool):
                record_assessment(GuardPreOnAssessment(
                    "BLOCKED", "persisted_resume_target_unavailable",
                ))
                return
            assessment = assess_main_guard_before_output_on(
                session_document=canonical,
                restored_guard=restored_guard,
                native_live=native_live,
                session_id=candidate.session_id or "",
                battery_id=candidate.battery_id or "",
                profile=str(canonical.get("profile") or ""),
                stage=str(canonical.get("stage") or ""),
                target_current_a=target_current,
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
            if assessment.status != "RECONCILED":
                return
            # Revalidate the exact candidate object and canonical identity,
            # revision and bytes immediately before issuing the one-use
            # capability consumed by canonical persistence restore.
            current_candidate = getattr(controller, "_guarded_restore_candidate", None)
            latest_again = read_canonical_session(SESSION_FILE)
            try:
                if not isinstance(latest_again, dict):
                    raise GuardJournalError("canonical_document_unavailable")
                _guard_again, revision_again = read_guard(
                    latest_again, session_id=candidate.session_id or "",
                    battery_id=candidate.battery_id or "", now_s=time.time(),
                )
            except (GuardJournalError, ValueError, TypeError, OverflowError) as exc:
                record_assessment(GuardPreOnAssessment(
                    "BLOCKED", "pre_activation_recheck_failed:" + type(exc).__name__,
                ))
                return
            if (current_candidate is not candidate
                    or not execution_port.session_recovery_guard.may_run_automatic_control()
                    or lock.owner_task is not asyncio.current_task()
                    or revision_again != candidate_revision
                    or latest_again.get("v2_trace_session_id") != candidate.session_id
                    or latest_again.get("v2_battery_id") != candidate.battery_id
                    or latest_again.get("state") == "retired"
                    or latest_again != canonical):
                record_assessment(GuardPreOnAssessment(
                    "BLOCKED", "candidate_or_canonical_changed_before_activation",
                ))
                return
            if candidate.canonical_bytes_sha256 is not None:
                try:
                    latest_bytes_match = (
                        hashlib.sha256(Path(SESSION_FILE).read_bytes()).hexdigest()
                        == candidate.canonical_bytes_sha256
                    )
                except OSError:
                    latest_bytes_match = False
                if not latest_bytes_match:
                    record_assessment(GuardPreOnAssessment(
                        "BLOCKED", "canonical_file_bytes_changed_before_activation",
                    ))
                    return
            try:
                permit = _issue_guarded_restore_activation_permit(
                    candidate=candidate, document=latest_again,
                    revision=revision_again, native_live=native_live,
                    owner_task=asyncio.current_task(),
                    owner_lock=lock,
                    canonical_bytes_sha256=candidate.canonical_bytes_sha256,
                )
            except (TypeError, ValueError, OverflowError) as exc:
                record_assessment(GuardPreOnAssessment(
                    "BLOCKED", "activation_permit_unavailable:" + type(exc).__name__,
                ))
                return
            # Latch all ordinary ON owners before canonical restore can mutate
            # any session state. A restore/extension rejection remains safe.
            execution_port.mark_guarded_restore_activated_off()
            controller._guarded_restore_activated_off = True
            # This is still an OFF-only source restore. No execution-port
            # writer is called here and output_is_on is explicit false.
            try:
                ok, _message = controller.try_restore_session(
                    0.0, 0.0, 0.0, output_is_on=False,
                    _guarded_activation_permit=permit,
                )
            except Exception as exc:
                record_assessment(GuardPreOnAssessment(
                    "BLOCKED", "canonical_guarded_restore_failed:" + type(exc).__name__,
                ))
                return
            if not ok:
                record_assessment(GuardPreOnAssessment(
                    "BLOCKED", "canonical_guarded_restore_rejected",
                ))
                return
            controller._guarded_restore_activation_candidate = candidate
            controller._guarded_restore_activation_generation = (
                int(getattr(controller, "_guarded_restore_activation_generation", 0)) + 1
            )
            execution_port.mark_guarded_restore_activated_off()
            self.last_guard_assessment = assessment
            return
        live = await execution_port.read_live()

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

        action = authorize_recovery_action(RecoveryAuthorizationInput(
            route=RecoveryRoute.IDLE_LINK,
            restored=True,
            auto_enable_authorized=True,
            safe_wait=False,
            input_voltage_ok=True,
            cold_start=True,
        ))
        if action is not RecoveryAction.SKIP:
            logger.error("Unexpected deferred startup cold-start authorization: %s", action)
            return
        logger.warning(
            "Cold-start automatic re-energization denied for deferred restored session"
        )

    @_serialized_deferred_restore
    async def guarded_physical_resume(self):
        """Assess a newly read Native snapshot and prepare a source-only resume.

        No production endpoint is installed: successful assessment yields
        READY_BUT_NOT_EXECUTED and preserves both OFF-only latches.
        """
        from runtime.charge.strategy.main_guard_pre_on import GuardPreOnAssessment
        from application.execution_port import GuardedPhysicalResumeResult

        app = self.app
        port = get_or_create_execution_port(app)
        controller = app.charge_controller
        lock = port._guard_owner_lock
        def blocked(reason):
            result = GuardPreOnAssessment("BLOCKED", reason)
            self.last_guard_assessment = result
            return GuardedPhysicalResumeResult("BLOCKED", reason)
        if (not port.guarded_restore_activated_off
                or not bool(getattr(controller, "_guarded_restore_activated_off", False))
                or not port.session_recovery_guard.may_run_automatic_control()
                or lock is None or lock.owner_task is not asyncio.current_task()):
            return blocked("guarded_resume_authority_unavailable")
        candidate = getattr(controller, "_guarded_restore_activation_candidate", None)
        if candidate is None or getattr(controller, "is_active", False) is not True:
            return blocked("restored_controller_or_candidate_missing")
        native_reader = getattr(app.hass, "get_native_guard_pre_on_snapshot", None)
        if not callable(native_reader):
            return blocked("direct_native_snapshot_api_unavailable")
        native = await native_reader()
        if native is None:
            return blocked("fresh_direct_native_evidence_unavailable")
        canonical = read_canonical_session(SESSION_FILE)
        try:
            if not isinstance(canonical, dict):
                return blocked("canonical_document_unavailable")
            digest = hashlib.sha256(Path(SESSION_FILE).read_bytes()).hexdigest()
            if candidate.canonical_bytes_sha256 is not None and digest != candidate.canonical_bytes_sha256:
                return blocked("canonical_file_bytes_changed")
            sid, bid = candidate.session_id or "", candidate.battery_id or ""
            guard, revision = read_guard(canonical, session_id=sid, battery_id=bid, now_s=time.time())
            target = canonical.get("target_current")
            if isinstance(target, bool) or not isinstance(target, (int, float)):
                return blocked("persisted_resume_target_unavailable")
            if (revision != candidate.guard_revision or canonical.get("v2_trace_session_id") != sid
                    or canonical.get("v2_battery_id") != bid
                    or canonical.get("state") == "retired"
                    or getattr(controller, "_v2_trace_session_id", None) != sid
                    or getattr(controller, "_v2_battery_id", None) != bid
                    or str(getattr(controller, "current_stage", "")) != str(canonical.get("stage"))
                    or str(getattr(controller, "battery_type", "")).upper() != str(canonical.get("profile", "")).upper()
                    or getattr(controller, "_main_current_guard", None) is None
                    or getattr(controller, "_main_current_guard_revision", None) != revision):
                return blocked("canonical_controller_guard_identity_changed")
            lease_meta = native.get("_lease_meta")
            lease_age = lease_meta.get("age_s") if isinstance(lease_meta, dict) else None
            lease_ok = (isinstance(lease_meta, dict) and lease_meta.get("source") == "esp_native_api"
                        and lease_meta.get("status") == "ok"
                        and lease_meta.get("native_type") == "BinarySensorState"
                        and isinstance(lease_age, (int, float)) and not isinstance(lease_age, bool)
                        and 0 <= lease_age <= 10.0 and as_bool(native.get("edge_lease_armed")) is True)
            assessment = assess_main_guard_before_output_on(
                session_document=canonical, restored_guard=controller._main_current_guard,
                native_live=native, session_id=sid, battery_id=bid,
                profile=str(canonical.get("profile") or ""), stage=str(canonical.get("stage") or ""),
                target_current_a=float(target), owner_authorized=True,
                edge_lease_armed=lease_ok, now_epoch_s=time.time(),
            )
            if assessment.status != "RECONCILED":
                self.last_guard_assessment = assessment
                return GuardedPhysicalResumeResult("BLOCKED", assessment.reason)
            if (read_canonical_session(SESSION_FILE) != canonical
                    or hashlib.sha256(Path(SESSION_FILE).read_bytes()).hexdigest() != digest
                    or lock.owner_task is not asyncio.current_task()
                    or not port.session_recovery_guard.may_run_automatic_control()):
                return blocked("canonical_or_owner_changed_before_resume")
            permit = issue_guarded_physical_resume_permit(
                candidate=candidate, document=canonical, revision=revision,
                native_live=native, owner_task=asyncio.current_task(), owner_lock=lock,
                controller=controller,
                activation_generation=getattr(controller, "_guarded_restore_activation_generation", 0),
                canonical_bytes_sha256=digest,
            )
        except (OSError, GuardJournalError, ValueError, TypeError, OverflowError) as exc:
            return blocked("guarded_resume_revalidation_failed:" + type(exc).__name__)
        self.last_guard_assessment = assessment
        return await port.execute_guarded_physical_resume(permit)


# Startup restore uptime reconciliation owns these two legacy constants.
UPTIME_AS_CHARGE_TIMER_MAX_SEC = 24 * 3600
UPTIME_SYNC_MAX_DRIFT_SEC = 300


def parse_uptime_to_elapsed_sec(uptime_raw: Any, *, now_s: float | None = None) -> Optional[float]:
    """Parse RD6018 uptime/timer telemetry into elapsed seconds."""
    from datetime import datetime

    if uptime_raw is None or uptime_raw == "":
        return None
    if isinstance(uptime_raw, (int, float)):
        return float(uptime_raw)
    value = str(uptime_raw).strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        pass
    if ":" in value and "T" not in value and "-" not in value:
        parts = value.split(":")
        try:
            if len(parts) == 2:
                a, b = int(parts[0].strip()), int(parts[1].strip())
                if a == 0:
                    return b * 60
                if 1 <= a <= 59 and b == 0:
                    return a * 60
                return a * 3600 + b * 60
            if len(parts) == 3:
                hours, minutes, seconds = (
                    int(parts[0].strip()), int(parts[1].strip()), int(parts[2].strip())
                )
                return hours * 3600 + minutes * 60 + seconds
        except (ValueError, IndexError):
            pass
    try:
        observed_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
        now_value = time.time() if now_s is None else float(now_s)
        elapsed = now_value - observed_at.timestamp()
        return None if elapsed < 0 else elapsed
    except Exception:
        return None


def sync_total_start_from_uptime(
    controller: Any,
    live: Optional[dict[str, Any]],
    *,
    max_drift_sec: int = UPTIME_SYNC_MAX_DRIFT_SEC,
    allow_init: bool = False,
    now_s: float | None = None,
) -> bool:
    """Reconcile total_start_time with the device timer under the legacy drift gate."""
    if not getattr(controller, "is_active", False):
        return False
    uptime_raw = (live or {}).get("uptime")
    if uptime_raw is None:
        return False
    now_value = time.time() if now_s is None else float(now_s)
    elapsed = parse_uptime_to_elapsed_sec(uptime_raw, now_s=now_value)
    if elapsed is None or not (0 < elapsed <= UPTIME_AS_CHARGE_TIMER_MAX_SEC):
        return False

    total_start = float(getattr(controller, "total_start_time", 0) or 0)
    if total_start > 0:
        if abs((now_value - total_start) - elapsed) > max_drift_sec:
            return False
    elif not allow_init:
        return False

    controller.total_start_time = now_value - elapsed
    return True


def apply_restore_time_corrections(
    controller: Any,
    live: Optional[dict[str, Any]],
    *,
    now_s: float | None = None,
) -> None:
    """Apply startup/reconnect clock reconciliation without owning session policy."""
    now_value = time.time() if now_s is None else float(now_s)
    link_lost = getattr(controller, "_link_lost_at", 0) or 0
    if link_lost > 0:
        gap = now_value - link_lost
        controller.total_start_time += gap
        controller.stage_start_time += gap
        clear_link_lost_timestamp(controller)
    sync_total_start_from_uptime(
        controller,
        live,
        max_drift_sec=UPTIME_SYNC_MAX_DRIFT_SEC,
        allow_init=False,
        now_s=now_value,
    )
