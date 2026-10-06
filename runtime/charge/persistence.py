"""Canonical charge-session persistence and restore owner."""

from __future__ import annotations

import json
import logging
import math
import os
import time
from typing import Any, Optional, Tuple

from charging_log import log_session_header
from runtime.charge.runtime.variables import STAGE_CLOCK_SANITY_MAX_HOURS
from runtime.charge.strategy.main_variables import AGM_STAGE_VOLTAGES_V
from runtime.charge.strategy.mix_variables import mix_finish_hold_seconds
from runtime.safety.variables import MAX_STAGE_CURRENT_A
from runtime.safety.voltage_variables import clamp_pb_automatic_target_voltage


logger = logging.getLogger("rd6018")

SESSION_FILE = "charge_session.json"
SESSION_MAX_AGE_S = 24 * 60 * 60
SESSION_START_MAX_AGE_S = 24 * 60 * 60

SESSION_MAX_AGE = SESSION_MAX_AGE_S
SESSION_START_MAX_AGE = SESSION_START_MAX_AGE_S
DONE_STATE_VERSION = 1
DONE_COMPLETION_STORAGE = "storage"
DONE_COMPLETION_TERMINAL = "terminal"
DONE_OUTPUT_ON = "on"
DONE_OUTPUT_OFF = "off"
AGM_STAGES = tuple(float(value) for value in AGM_STAGE_VOLTAGES_V.default)
MAX_STAGE_CURRENT = float(MAX_STAGE_CURRENT_A.default)
MIX_DONE_TIMER = mix_finish_hold_seconds()
ELAPSED_MAX_HOURS = float(STAGE_CLOCK_SANITY_MAX_HOURS.default)

def _set_done_outcome(
    host: Any,
    completion_kind: Optional[str],
    output_intent: str,
    *,
    authoritative: bool,
) -> None:
    host._done_completion_kind = completion_kind
    host._done_output_intent = output_intent
    host._done_outcome_authoritative = bool(authoritative)


def _explicit_storage_outcome(document: dict[str, Any]) -> bool:
    return (
        document.get("done_state_version") == DONE_STATE_VERSION
        and document.get("completion_kind") == DONE_COMPLETION_STORAGE
        and document.get("output_intent") == DONE_OUTPUT_ON
    )


def restore_allows_auto_enable(host: Any) -> bool:
    """Allow auto-enable only for active sessions or explicit managed Storage."""
    if host.current_stage == host.STAGE_DONE:
        return bool(
            getattr(host, "_done_outcome_authoritative", False)
            and getattr(host, "_done_completion_kind", None)
            == DONE_COMPLETION_STORAGE
            and getattr(host, "_done_output_intent", DONE_OUTPUT_OFF)
            == DONE_OUTPUT_ON
        )
    cooling_stage = getattr(host, "STAGE_COOLING", None)
    if cooling_stage is not None and host.current_stage == cooling_stage:
        return False
    return True


def paused_done_resume_is_authorized(
    app: Any,
    host: Any,
    *,
    session_file: Optional[str] = None,
) -> bool:
    """Guard operator-pause resume before a dormant Done session is restored."""
    session_file = SESSION_FILE if session_file is None else session_file
    pause_active = getattr(app, "_operator_pause_active", None)
    if not callable(pause_active) or not bool(pause_active()):
        return True
    if host.current_stage == host.STAGE_DONE:
        return restore_allows_auto_enable(host)
    if bool(getattr(host, "is_active", False)):
        return True
    if not os.path.exists(session_file):
        return True
    try:
        with open(session_file, "r", encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, json.JSONDecodeError, TypeError):
        return True
    if document.get("stage") != host.STAGE_DONE:
        return True
    return _explicit_storage_outcome(document)





def _normalize_terminal_done_document(
    document: dict[str, Any],
    *,
    session_file: str,
) -> None:
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

    tmp_path = f"{session_file}.done-normalize.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(normalized, handle, ensure_ascii=False, indent=2)
        os.replace(tmp_path, session_file)
    except OSError as ex:
        logger.warning("Could not normalize terminal Done session: %s", ex)
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass


def clear_session_file(host: Any, *, session_file: str = SESSION_FILE) -> None:
        """Удалить файл сессии."""
        try:
            if os.path.exists(session_file):
                os.remove(session_file)
        except OSError:
            pass

def save_session(host: Any, voltage: float, current: float, ah: float, *, session_file: str = SESSION_FILE) -> None:
        """Сохранить текущее состояние в charge_session.json. Уставки — с прибора, если известны."""
        if host.current_stage == host.STAGE_IDLE:
            return

        if host.current_stage == host.STAGE_DONE:
            source_stage = getattr(host, "_done_transition_source_stage", None)
            if (
                source_stage == host.STAGE_SAFE_WAIT
                and getattr(host, "previous_stage", None) == host.STAGE_SAFE_WAIT
            ):
                _set_done_outcome(
                    host,
                    DONE_COMPLETION_STORAGE,
                    DONE_OUTPUT_ON,
                    authoritative=True,
                )
            elif not bool(getattr(host, "_done_outcome_authoritative", False)):
                _set_done_outcome(
                    host,
                    DONE_COMPLETION_TERMINAL,
                    DONE_OUTPUT_OFF,
                    authoritative=True,
                )
        else:
            _set_done_outcome(host, None, DONE_OUTPUT_OFF, authoritative=False)

        done_storage = bool(
            host.current_stage == host.STAGE_DONE
            and getattr(host, "_done_outcome_authoritative", False)
            and getattr(host, "_done_completion_kind", None) == DONE_COMPLETION_STORAGE
            and getattr(host, "_done_output_intent", DONE_OUTPUT_OFF) == DONE_OUTPUT_ON
        )
        target_finish = host._get_target_finish_time()
        if done_storage:
            uv, ui = host._storage_target()
            target_finish = None
        elif host.current_stage == host.STAGE_SAFE_WAIT:
            uv, ui = host._safe_wait_target_v, host._safe_wait_target_i
        elif host.current_stage == host.STAGE_COOLING:
            uv, ui = host._cooling_target_v, host._cooling_target_i
        else:
            uv, ui = host._get_target_v_i()
        # Сохраняем фактические уставки прибора (до потери связи/перезапуска).
        # Explicit Storage Done is the exception: the queued Storage target is
        # authoritative even when the last physical readback is still the old HV program.
        if (
            not done_storage
            and host._device_set_voltage is not None
            and host._device_set_voltage > 0
            and host._device_set_current is not None
            and host._device_set_current > 0
        ):
            uv, ui = host._device_set_voltage, host._device_set_current
        elif not done_storage:
            # С прибора уставки не приходили — не перезаписывать дефолтами профиля; сохранить из файла, если есть
            if os.path.exists(session_file):
                try:
                    with open(session_file, "r", encoding="utf-8") as f:
                        old = json.load(f)
                    tv, ti = float(old.get("target_voltage", 0) or 0), float(old.get("target_current", 0) or 0)
                    if tv > 0 and ti > 0:
                        uv, ui = tv, ti
                except (OSError, json.JSONDecodeError, TypeError, ValueError):
                    pass
        previous_terminal_metadata = {}
        if os.path.exists(session_file):
            try:
                with open(session_file, "r", encoding="utf-8") as f:
                    previous_document = json.load(f)
                if isinstance(previous_document, dict) and isinstance(
                    previous_document.get("terminal_metadata"), dict
                ):
                    previous_terminal_metadata = previous_document["terminal_metadata"]
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass

        def terminal_measurement(name: str, value: Any) -> Tuple[Optional[float], bool]:
            """Keep only evidenced positive measurements; never replace them with defaults."""
            try:
                candidate = float(value)
            except (TypeError, ValueError, OverflowError):
                candidate = 0.0
            if math.isfinite(candidate) and candidate > 0.0:
                return candidate, True
            try:
                previous = float(previous_terminal_metadata.get(name))
            except (TypeError, ValueError, OverflowError):
                previous = 0.0
            if math.isfinite(previous) and previous > 0.0:
                return previous, True
            return None, False

        saved_at = time.time()
        terminal = host.current_stage == host.STAGE_DONE
        terminal_voltage, terminal_voltage_available = terminal_measurement("voltage", voltage)
        terminal_current, terminal_current_available = terminal_measurement("current", current)
        terminal_ah, terminal_ah_available = terminal_measurement("ah", ah)
        data = {
            "profile": host.battery_type,
            "stage": host.current_stage,
            "stage_start_time": host.stage_start_time,
            "target_finish_time": target_finish,
            "finish_timer_start": host.finish_timer_start,
            "ah_limit": host.ah_capacity,
            "start_ah": host._start_ah,
            "stage_start_ah": host._stage_start_ah,
            "stage_start_voltage": host._stage_start_voltage,
            "stage_start_current": host._stage_start_current,
            "stage_start_temp": host._stage_start_temp,
            "current_retries": host.antisulfate_count,
            "target_voltage": uv,
            "target_current": ui,
            "agm_stage_idx": host._agm_stage_idx,
            "safe_wait_next_stage": host._safe_wait_next_stage,
            "safe_wait_target_v": host._safe_wait_target_v,
            "safe_wait_target_i": host._safe_wait_target_i,
            "safe_wait_start": host._safe_wait_start,
            "total_start_time": host.total_start_time,  # v2.6: сохраняем общий старт
            "first_stage_hold_since": host._first_stage_hold_since,
            "first_stage_hold_current": host._first_stage_hold_current,
            "stuck_current_since": host._stuck_current_since,
            "stuck_current_value": host._stuck_current_value,
            "previous_stage": host.previous_stage,
            "last_transition_reason": host._last_transition_reason,
            "stage_history": list(host._stage_history),
            "saved_at": saved_at,
            "terminal_state_at": host.stage_start_time if terminal else None,
            "terminal_session_id": getattr(host, "_v2_trace_session_id", None) if terminal else None,
            "done_state_version": DONE_STATE_VERSION if terminal else None,
            "completion_kind": (
                getattr(host, "_done_completion_kind", DONE_COMPLETION_TERMINAL)
                if terminal
                else None
            ),
            "output_intent": (
                getattr(host, "_done_output_intent", DONE_OUTPUT_OFF)
                if terminal
                else None
            ),
            "terminal_metadata": {
                "stage": host.STAGE_DONE,
                "reason": host._last_transition_reason,
                "completion_kind": getattr(
                    host, "_done_completion_kind", DONE_COMPLETION_TERMINAL
                ),
                "output_intent": getattr(host, "_done_output_intent", DONE_OUTPUT_OFF),
                "voltage": terminal_voltage,
                "current": terminal_current,
                "ah": terminal_ah,
                "availability": {
                    "voltage": terminal_voltage_available,
                    "current": terminal_current_available,
                    "ah": terminal_ah_available,
                },
            } if terminal else None,
        }
        try:
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as ex:
            logger.warning("Could not save session: %s", ex)

def restore_session(
    host: Any,
    voltage: float,
    current: float,
    ah: float,
    *,
    session_file: str = SESSION_FILE,
) -> Tuple[bool, Optional[str]]:
        """
        Восстановить сессию из файла, если прошло < 60 мин.
        Возвращает (ok, notify_message).
        """
        if not os.path.exists(session_file):
            return False, None
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return False, None

        saved_at = data.get("saved_at", 0)
        if time.time() - saved_at > SESSION_MAX_AGE:
            host._clear_session_file()
            return False, None

        host._stage_tracking_enabled = False
        host.battery_type = data.get("profile", host.PROFILE_CA)
        host.ah_capacity = int(data.get("ah_limit", 60))
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
        host.antisulfate_count = int(data.get("current_retries", 0))
        host._agm_stage_idx = int(data.get("agm_stage_idx", 0))
        host._agm_stage_idx = max(0, min(host._agm_stage_idx, len(AGM_STAGES) - 1))
        host._start_ah = float(data.get("start_ah", 0))
        host._stage_start_ah = float(data.get("stage_start_ah", ah))  # при отсутствии — текущий ah
        try:
            host._stage_start_voltage = float(data.get("stage_start_voltage", voltage))
        except (TypeError, ValueError):
            host._stage_start_voltage = float(voltage)
        try:
            host._stage_start_current = float(data.get("stage_start_current", current))
        except (TypeError, ValueError):
            host._stage_start_current = float(current)
        try:
            host._stage_start_temp = float(data.get("stage_start_temp", 0.0))
        except (TypeError, ValueError):
            host._stage_start_temp = 0.0
        host._safe_wait_next_stage = data.get("safe_wait_next_stage")
        host._safe_wait_target_v = float(data.get("safe_wait_target_v", 0))
        host._safe_wait_target_i = float(data.get("safe_wait_target_i", 0))
        now = time.time()
        host.previous_stage = data.get("previous_stage")
        host._last_transition_reason = str(data.get("last_transition_reason", "") or "")
        host._stage_history.clear()
        raw_stage_history = data.get("stage_history", [])
        if isinstance(raw_stage_history, list):
            for item in raw_stage_history[-host._stage_history.maxlen:]:
                if not isinstance(item, dict):
                    continue
                from_stage = str(item.get("from") or "").strip()
                to_stage = str(item.get("to") or "").strip()
                if not from_stage and not to_stage:
                    continue
                host._stage_history.append(
                    {
                        "from": from_stage,
                        "to": to_stage,
                        "reason": str(item.get("reason") or "").strip(),
                        "ts": float(item.get("ts") or now),
                    }
                )
        if host._stage_history and not host.previous_stage:
            last_transition = host._stage_history[-1]
            host.previous_stage = str(last_transition.get("from") or "") or None
        raw_safe_wait_start = data.get("safe_wait_start")
        try:
            host._safe_wait_start = float(raw_safe_wait_start) if raw_safe_wait_start not in (None, 0) else now
        except (TypeError, ValueError):
            host._safe_wait_start = now
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
        raw_hold_since = data.get("first_stage_hold_since")
        try:
            host._first_stage_hold_since = float(raw_hold_since) if raw_hold_since not in (None, 0) else None
        except (TypeError, ValueError):
            host._first_stage_hold_since = None
        raw_hold_current = data.get("first_stage_hold_current")
        try:
            host._first_stage_hold_current = float(raw_hold_current) if raw_hold_current is not None else None
        except (TypeError, ValueError):
            host._first_stage_hold_current = None
        raw_stuck_since = data.get("stuck_current_since")
        try:
            host._stuck_current_since = float(raw_stuck_since) if raw_stuck_since not in (None, 0) else None
        except (TypeError, ValueError):
            host._stuck_current_since = None
        raw_stuck_value = data.get("stuck_current_value")
        try:
            host._stuck_current_value = float(raw_stuck_value) if raw_stuck_value is not None else None
        except (TypeError, ValueError):
            host._stuck_current_value = None

        # v2.6: восстанавливаем общий старт сессии
        raw_total_start = data.get("total_start_time")
        try:
            host.total_start_time = float(raw_total_start) if raw_total_start not in (None, 0) else now
        except (TypeError, ValueError):
            host.total_start_time = now
        # Валидация total_start_time
        if not host.total_start_time or host.total_start_time <= 0 or (now - host.total_start_time) > SESSION_START_MAX_AGE:
            host.total_start_time = now
            logger.info("Restore: total_start_time invalid or >24h, set to now()")

        target_finish = data.get("target_finish_time")
        restored_terminal = False
        target_v_raw = float(data.get("target_voltage", 14.7))
        target_v = clamp_pb_automatic_target_voltage(target_v_raw)
        if abs(target_v - target_v_raw) >= 0.01:
            logger.warning("Restore: target voltage clamped %.2fV -> %.2fV", target_v_raw, target_v)
        target_i = float(data.get("target_current", 1.0))
        target_i = min(MAX_STAGE_CURRENT, max(0.1, target_i))
        host._restored_target_v = target_v
        host._restored_target_i = target_i
        host.finish_timer_start = data.get("finish_timer_start")
        raw_stage_start = data.get("stage_start_time")
        try:
            saved_stage_start = float(raw_stage_start) if raw_stage_start not in (None, 0) else now
        except (TypeError, ValueError):
            saved_stage_start = now
        # Фикс "1970 года": если start_time отсутствует, 0 или старше 24 ч — принудительно now()
        if not saved_stage_start or saved_stage_start <= 0 or (now - saved_stage_start) > SESSION_START_MAX_AGE:
            saved_stage_start = now
            logger.info("Restore: start_time invalid or >24h, set to now()")

        host._session_start_reason = "Auto-restore"

        if target_finish is not None:
            remaining_sec = target_finish - now
            if remaining_sec > 0:
                if host.current_stage == host.STAGE_DESULFATION:
                    phase_dur = 2 * 3600
                    host.stage_start_time = now - (phase_dur - remaining_sec)
                elif host.current_stage == host.STAGE_MIX and host.finish_timer_start is not None:
                    host.finish_timer_start = target_finish - MIX_DONE_TIMER
                else:
                    if saved_stage_start and 0 < saved_stage_start <= now:
                        host.stage_start_time = saved_stage_start
                    else:
                        host.stage_start_time = now
                remaining_min = int(remaining_sec / 60)
                msg = (
                    f"🔄 <b>Сессия восстановлена!</b>\n\n"
                    f"Продолжаю режим: <code>{host.current_stage}</code>.\n"
                    f"Осталось времени: <code>{remaining_min}</code> мин.\n"
                    f"Цель: <code>{target_v:.1f}</code>В / <code>{target_i:.2f}</code>А"
                )
            else:
                if host.current_stage == host.STAGE_DESULFATION:
                    host.current_stage = host.STAGE_MAIN
                    host._clear_restored_targets()
                    host.stage_start_time = now
                elif host.current_stage == host.STAGE_MIX:
                    host.current_stage = host.STAGE_DONE
                    host._clear_restored_targets()
                    host.stage_start_time = now
                    restored_terminal = True
                remaining_min = 0
                msg = (
                    f"🔄 <b>Сессия восстановлена!</b>\n\n"
                    f"Переход к следующей фазе: <code>{host.current_stage}</code>.\n"
                    f"Цель: <code>{target_v:.1f}</code>В / <code>{target_i:.2f}</code>А"
                )
        else:
            remaining_min = 0
            host.stage_start_time = saved_stage_start if saved_stage_start and saved_stage_start <= now else now
            msg = (
                f"🔄 <b>Сессия восстановлена!</b>\n\n"
                f"Продолжаю режим: <code>{host.current_stage}</code>.\n"
                f"Цель: <code>{target_v:.1f}</code>В / <code>{target_i:.2f}</code>А"
            )

        host._reset_delta_and_blanking(now)
        host._temp_comp_last_update_time = 0.0
        host._temp_comp_last_temp = None
        if host.current_stage == host.STAGE_MAIN:
            raw_stuck_since = data.get("stuck_current_since")
            try:
                host._stuck_current_since = float(raw_stuck_since) if raw_stuck_since not in (None, 0) else None
            except (TypeError, ValueError):
                host._stuck_current_since = None
            raw_stuck_value = data.get("stuck_current_value")
            try:
                host._stuck_current_value = float(raw_stuck_value) if raw_stuck_value is not None else None
            except (TypeError, ValueError):
                host._stuck_current_value = None
        if host.current_stage != host.STAGE_MIX:
            host.finish_timer_start = None

        # Синхронизация таймеров с прибором: оцениваем время по накопленным А·ч и току
        i_avg = max(float(current), 0.1)
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
        if restored_terminal:
            host._save_session(voltage, current, ah)
        elif normalize_done_document:
            _normalize_terminal_done_document(data, session_file=session_file)
        host._stage_tracking_enabled = True
        return True, msg

__all__ = [
    "DONE_COMPLETION_STORAGE",
    "DONE_COMPLETION_TERMINAL",
    "DONE_OUTPUT_OFF",
    "DONE_OUTPUT_ON",
    "DONE_STATE_VERSION",
    "SESSION_FILE",
    "SESSION_MAX_AGE_S",
    "SESSION_START_MAX_AGE_S",
    "clear_session_file",
    "paused_done_resume_is_authorized",
    "restore_allows_auto_enable",
    "restore_session",
    "save_session",
]
