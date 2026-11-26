"""Persisted charge-session admission and controller restore use case."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional, Tuple

from charging_log import log_session_header
from runtime.charge.runtime.variables import STAGE_CLOCK_SANITY_MAX_HOURS
from runtime.charge.strategy.main_variables import AGM_STAGE_VOLTAGES_V
from runtime.charge.strategy.mix_variables import mix_finish_hold_seconds
from runtime.safety.variables import MAX_STAGE_CURRENT_A
from runtime.safety.voltage_variables import clamp_pb_automatic_target_voltage
from runtime.charge.session_document_projection import _set_done_outcome
from runtime.charge.start_pending import _pending_start_document
from runtime.charge.session import restore_stage_history
from runtime.charge.terminal_intent import (
    DONE_COMPLETION_STORAGE, DONE_COMPLETION_TERMINAL, DONE_OUTPUT_ON, DONE_OUTPUT_OFF,
)
from runtime.charge.restore_admission import (
    DONE_STATE_VERSION, _explicit_storage_outcome, INTERRUPTION_OWNER,
    INTERRUPTION_REASON, validate_interruption_marker,
)
from runtime.charge.restore_projection import (
    project_restore_scalars, project_restore_stage_timeline,
)
from runtime.charge.restore_finalization import finalize_restored_session

logger = logging.getLogger("rd6018")

SESSION_FILE = "charge_session.json"
SESSION_MAX_AGE_S = 24 * 60 * 60
SESSION_START_MAX_AGE_S = 24 * 60 * 60
SESSION_MAX_AGE = SESSION_MAX_AGE_S
SESSION_START_MAX_AGE = SESSION_START_MAX_AGE_S
AGM_STAGES = tuple(float(value) for value in AGM_STAGE_VOLTAGES_V.default)
MAX_STAGE_CURRENT = float(MAX_STAGE_CURRENT_A.default)
MIX_DONE_TIMER = mix_finish_hold_seconds()
ELAPSED_MAX_HOURS = float(STAGE_CLOCK_SANITY_MAX_HOURS.default)

def _normalize_terminal_done_document(
    host: Any,
    document: dict[str, Any],
    *,
    session_file: str,
) -> bool:
    """Normalize ambiguous legacy Done to terminal/OFF without rewriting evidence."""

    normalized = dict(document)
    normalized["done_state_version"] = DONE_STATE_VERSION
    normalized["completion_kind"] = DONE_COMPLETION_TERMINAL
    normalized["output_intent"] = DONE_OUTPUT_OFF

    terminal_metadata = normalized.get("terminal_metadata")
    if isinstance(terminal_metadata, dict):
        terminal_metadata = dict(terminal_metadata)
        terminal_metadata["completion_kind"] = DONE_COMPLETION_TERMINAL
        terminal_metadata["output_intent"] = DONE_OUTPUT_OFF
        normalized["terminal_metadata"] = terminal_metadata

    from runtime.charge.session_atomic import complete_session_document
    normalized = complete_session_document(
        host, normalized, previous=document, now_s=time.time(),
    )
    document.clear()
    document.update(normalized)
    return True


def restore_session(
    host: Any,
    voltage: float,
    current: float,
    ah: float,
    *,
    session_file: str = SESSION_FILE,
    _guarded_activation_permit: Any = None,
) -> Tuple[bool, Optional[str]]:
        """
        Восстановить сессию из файла, если прошло < 60 мин.
        Возвращает (ok, notify_message).
        """
        if not os.path.exists(session_file):
            return False, None
        try:
            raw_bytes = Path(session_file).read_bytes()
            raw_document = raw_bytes.decode("utf-8")
            data = json.loads(raw_document)
        except (OSError, UnicodeError, json.JSONDecodeError):
            return False, None

        if not isinstance(data, dict):
            return False, None
        if _pending_start_document(data):
            return False, "A START transaction envelope requires reconciliation; automatic restore is disabled."
        interruption = validate_interruption_marker(data)
        if interruption == "interrupted":
            return False, "This charge session was interrupted by process restart; automatic restore is disabled."
        if interruption == "blocked":
            return False, "Interruption marker is invalid; automatic restore is disabled."
        # Verify optional immutable native recipe selection *before* restoring
        # any controller fields. A corrupted or wrong-profile snapshot cannot
        # silently become a normal AUTO session.
        from runtime.charge.programs.native_recipe_session import (
            restore_native_selection,
        )
        try:
            selected_native = restore_native_selection(
                data, profile=data.get("profile"), intent=data.get("v2_intent"),
            )
        except (ValueError, TypeError, KeyError) as exc:
            return False, f"Native recipe session selection invalid: {exc}"
        # A recovery-retired record is terminal evidence, never an old session.
        # Reject before mutating any controller fields.
        if data.get("owner") == "runtime.charge.persistence" and data.get("state") == "retired":
            if (data.get("schema_version") == 1 and data.get("stage") == "RETIRED"
                    and data.get("retirement_kind") == "operator_recovery_clearance"
                    and data.get("output_intent") == "verified_off"
                    and data.get("verified_off_transaction_id")
                    and data.get("verified_off_recorded_utc")
                    and data.get("session_id") and "battery_id" in data and data.get("retired_utc")):
                return False, "This charge session was explicitly retired; start a fresh session."
            return False, "Retired session record is invalid; automatic restore is disabled."
        # Guarded MAIN snapshots carry monotone electrical authority. They
        # remain quarantined unless the canonical startup owner supplies its
        # one-transaction, current-task activation capability.
        from runtime.charge.strategy.main_guard_session import GUARD_KEY
        if GUARD_KEY in data:
            from runtime.charge.session import (
                GuardedRestoreCandidate,
                _valid_guarded_restore_activation_permit,
            )
            from runtime.charge.strategy.main_guard_session import GuardJournalError, read_guard
            try:
                sid = str(data.get("v2_trace_session_id") or "")
                bid = str(data.get("v2_battery_id") or "")
                restored_guard, revision = read_guard(
                    data, session_id=sid, battery_id=bid, now_s=time.time(),
                )
            except (GuardJournalError, ValueError, TypeError, OverflowError):
                restored_guard, revision = None, None
            permit_valid = (
                restored_guard is not None and restored_guard.pending is None
                and restored_guard.fault is None
                and _valid_guarded_restore_activation_permit(
                    _guarded_activation_permit, document=data, session_id=sid,
                    battery_id=bid, revision=revision,
                    candidate=getattr(host, "_guarded_restore_candidate", None),
                    canonical_bytes_sha256=hashlib.sha256(raw_bytes).hexdigest(),
                )
            )
            if not permit_valid:
                host._guarded_restore_candidate = GuardedRestoreCandidate.capture(
                    data, "direct_native_pre_on_reconciliation_required",
                    canonical_bytes=raw_bytes,
                )
                return False, (
                    "MAIN Current Guard session is held for owner/readback "
                    "reconciliation; automatic resume is disabled."
                )
        saved_at = data.get("saved_at", 0)
        if time.time() - saved_at > SESSION_MAX_AGE:
            host._clear_session_file()
            return False, None

        scalars = project_restore_scalars(
            data, ah=ah, voltage=voltage, current=current,
            agm_stage_count=len(AGM_STAGES), max_stage_current=MAX_STAGE_CURRENT,
            clamp_voltage=clamp_pb_automatic_target_voltage,
        )
        now = time.time()
        future_profile = data.get("profile", host.PROFILE_CA)
        future_total_start_time = scalars.total_start_time or now
        if (not future_total_start_time or future_total_start_time <= 0
                or (now - future_total_start_time) > SESSION_START_MAX_AGE):
            future_total_start_time = now
        from runtime.charge.session import (
            prepare_trace_identity_application,
            project_trace_identity,
        )
        configuration = getattr(host, "host_configuration", None)
        intent_default = getattr(
            configuration, "restore_trace_default_intent",
            getattr(host, "_v2_intent", "normal"),
        )
        condition_default = getattr(
            configuration, "restore_trace_default_condition",
            getattr(host, "_v2_condition_before", "unknown"),
        )
        preprojected_trace = project_trace_identity(
            data,
            total_start_time=future_total_start_time,
            battery_type=future_profile,
            ah_capacity=scalars.ah_limit,
            battery_id=getattr(host, "_v2_battery_id", None),
            intent_default=intent_default,
            condition_default=condition_default,
            now_s=now,
        )
        prepared_trace_values = prepare_trace_identity_application(
            host, preprojected_trace,
        )

        # Timeline continuation is a pure projection over the accepted
        # document and canonical host constants. Compute it before the first
        # active-session mutation so projection failures remain pre-apply.
        target_finish = scalars.target_finish_time
        target_v_raw = scalars.target_voltage_raw
        target_v = scalars.target_voltage
        target_i = scalars.target_current
        saved_stage_start = scalars.stage_start_time if scalars.stage_start_time is not None else now
        if (not saved_stage_start or saved_stage_start <= 0
                or (now - saved_stage_start) > SESSION_START_MAX_AGE):
            saved_stage_start = now
        timeline = project_restore_stage_timeline(
            current_stage=data.get("stage", host.STAGE_MAIN),
            main_stage=host.STAGE_MAIN,
            mix_stage=host.STAGE_MIX,
            desulfation_stage=host.STAGE_DESULFATION,
            done_stage=host.STAGE_DONE,
            now=now,
            target_finish_time=target_finish,
            saved_stage_start=saved_stage_start,
            existing_finish_timer_start=data.get("finish_timer_start"),
            mix_done_timer=MIX_DONE_TIMER,
        )

        if GUARD_KEY in data:
            host._main_current_guard = restored_guard
            host._main_current_guard_revision = revision

        host._native_recipe_session_selection = selected_native
        host._stage_tracking_enabled = False
        host.battery_type = data.get("profile", host.PROFILE_CA)
        host.ah_capacity = scalars.ah_limit
        host.current_stage = data.get("stage", host.STAGE_MAIN)
        normalize_done_document = False
        if host.current_stage == host.STAGE_DONE:
            if _explicit_storage_outcome(data):
                _set_done_outcome(
                    host,
                    DONE_COMPLETION_STORAGE,
                    DONE_OUTPUT_ON,
                    authoritative=True,
                )
            else:
                _set_done_outcome(
                    host,
                    DONE_COMPLETION_TERMINAL,
                    DONE_OUTPUT_OFF,
                    authoritative=True,
                )
                normalize_done_document = True
        else:
            _set_done_outcome(host, None, DONE_OUTPUT_OFF, authoritative=False)
        host.antisulfate_count = scalars.current_retries
        host._agm_stage_idx = scalars.agm_stage_idx
        host._start_ah = scalars.start_ah
        host._stage_start_ah = scalars.stage_start_ah
        host._stage_start_voltage = scalars.stage_start_voltage
        host._stage_start_current = scalars.stage_start_current
        host._stage_start_temp = scalars.stage_start_temp
        host._safe_wait_next_stage = data.get("safe_wait_next_stage")
        host._safe_wait_target_v = scalars.safe_wait_target_v
        host._safe_wait_target_i = scalars.safe_wait_target_i
        restore_stage_history(
            host, data.get("previous_stage"), data.get("last_transition_reason"),
            data.get("stage_history", []), now=now,
        )
        host._safe_wait_start = scalars.safe_wait_start if scalars.safe_wait_start is not None else now
        if host.current_stage == host.STAGE_SAFE_WAIT:
            allowed_safe_wait_next = {host.STAGE_MAIN, host.STAGE_DONE}
            if host._safe_wait_next_stage not in allowed_safe_wait_next:
                logger.warning(
                    "Restore: invalid safe_wait_next_stage=%r, fallback to %s",
                    host._safe_wait_next_stage,
                    host.STAGE_MAIN,
                )
                host._safe_wait_next_stage = host.STAGE_MAIN
        else:
            host._safe_wait_next_stage = None
        host._first_stage_hold_since = scalars.first_stage_hold_since
        host._first_stage_hold_current = scalars.first_stage_hold_current
        host._stuck_current_since = scalars.stuck_current_since
        host._stuck_current_value = scalars.stuck_current_value

        # v2.6: восстанавливаем общий старт сессии
        host.total_start_time = scalars.total_start_time if scalars.total_start_time is not None else now
        # Валидация total_start_time
        if not host.total_start_time or host.total_start_time <= 0 or (now - host.total_start_time) > SESSION_START_MAX_AGE:
            host.total_start_time = now
            logger.info("Restore: total_start_time invalid or >24h, set to now()")

        from runtime.charge.session import apply_trace_identity
        apply_trace_identity(
            host, preprojected_trace, prepared=prepared_trace_values,
        )

        restored_terminal = False
        if abs(target_v - target_v_raw) >= 0.01:
            logger.warning("Restore: target voltage clamped %.2fV -> %.2fV", target_v_raw, target_v)
        host._restored_target_v = target_v
        host._restored_target_i = target_i
        host.finish_timer_start = data.get("finish_timer_start")
        # Фикс "1970 года": если start_time отсутствует, 0 или старше 24 ч — принудительно now()
        if not saved_stage_start or saved_stage_start <= 0 or (now - saved_stage_start) > SESSION_START_MAX_AGE:
            saved_stage_start = now
            logger.info("Restore: start_time invalid or >24h, set to now()")

        host._session_start_reason = "Auto-restore"

        host.current_stage = timeline.stage
        if timeline.clear_restored_targets:
            host._clear_restored_targets()
        if timeline.stage_start_time is not None:
            host.stage_start_time = timeline.stage_start_time
        if timeline.update_finish_timer_start:
            host.finish_timer_start = timeline.finish_timer_start
        restored_terminal = timeline.restored_terminal
        normalize_done_document = bool(normalize_done_document or restored_terminal)
        remaining_min = timeline.remaining_min

        if target_finish is not None:
            remaining_sec = target_finish - now
            if remaining_sec > 0:
                msg = (
                    f"🔄 <b>Сессия восстановлена!</b>\n\n"
                    f"Продолжаю режим: <code>{host.current_stage}</code>.\n"
                    f"Осталось времени: <code>{remaining_min}</code> мин.\n"
                    f"Цель: <code>{target_v:.1f}</code>В / <code>{target_i:.2f}</code>А"
                )
            else:
                msg = (
                    f"🔄 <b>Сессия восстановлена!</b>\n\n"
                    f"Переход к следующей фазе: <code>{host.current_stage}</code>.\n"
                    f"Цель: <code>{target_v:.1f}</code>В / <code>{target_i:.2f}</code>А"
                )
        else:
            msg = (
                f"🔄 <b>Сессия восстановлена!</b>\n\n"
                f"Продолжаю режим: <code>{host.current_stage}</code>.\n"
                f"Цель: <code>{target_v:.1f}</code>В / <code>{target_i:.2f}</code>А"
            )

        host._reset_delta_and_blanking(now)
        host._temp_comp_last_update_time = 0.0
        host._temp_comp_last_temp = None
        if host.current_stage == host.STAGE_MAIN:
            host._stuck_current_since = scalars.stuck_current_since
            host._stuck_current_value = scalars.stuck_current_value
        if host.current_stage != host.STAGE_MIX:
            host.finish_timer_start = None

        # Синхронизация таймеров с прибором: оцениваем время по накопленным А·ч и току
        i_avg = scalars.measured_average_current
        delta_ah_total = ah - host._start_ah
        delta_ah_stage = ah - host._stage_start_ah
        if delta_ah_total > 0.01 and i_avg > 0.05:
            est_total_h = delta_ah_total / i_avg
            est_total_h = min(est_total_h, SESSION_START_MAX_AGE / 3600)
            host.total_start_time = now - est_total_h * 3600
            logger.info("Restore: total_start_time synced from Ah: %.1f h elapsed", est_total_h)
        if delta_ah_stage > 0.01 and i_avg > 0.05:
            est_stage_h = delta_ah_stage / i_avg
            est_stage_h = min(est_stage_h, SESSION_START_MAX_AGE / 3600)
            host.stage_start_time = now - est_stage_h * 3600
            logger.info("Restore: stage_start_time synced from Ah: %.1f h on stage", est_stage_h)

        elapsed_sec = now - host.stage_start_time
        if elapsed_sec < 0 or elapsed_sec > ELAPSED_MAX_HOURS * 3600:
            host.stage_start_time = now
            logger.warning("Restore: stage_start_time corrected (elapsed invalid)")
        restored_stage_limit = host._get_stage_max_hours()
        restored_target_v, restored_target_i = host._get_target_v_i()
        log_session_header(
            "restore",
            host.current_stage,
            voltage,
            current,
            0.0,
            ah,
            host.battery_type,
            host.ah_capacity,
            host._session_rules_summary(),
            meta={
                "session_reason": host._session_start_reason,
                "stage_limit_h": f"{restored_stage_limit:.1f}" if restored_stage_limit is not None else "—",
                "target_v": f"{restored_target_v:.2f}",
                "target_i": f"{restored_target_i:.2f}",
                "remaining_min": remaining_min,
            },
        )
        finalize_restored_session(
            host,
            data,
            normalize_done_document=normalize_done_document,
            normalize_terminal=_normalize_terminal_done_document,
            session_file=session_file,
            canonical_preimage=raw_bytes,
            restored_terminal=restored_terminal,
            voltage=voltage,
            current=current,
            ah=ah,
        )
        return True, msg
