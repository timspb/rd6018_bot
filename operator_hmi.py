from __future__ import annotations

import asyncio
import html
import math
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional

from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from manual_mode import MANUAL_MIX_FINISH_HOLD_SEC
from rd6018_telemetry import telemetry_freshness
from application.operator_views import OperatorDetailsView, ServiceDetailsView
from application.operator_actions import OperatorAction, OperatorActionSpec, OperatorActionsView
from application.intents import OperatorIntent, OperatorIntentKind


class HmiProcessState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STORAGE = "storage"
    CONTAINMENT = "containment"
    HANDS_OFF = "hands_off"
    ADOPTED_MIX = "adopted_mix"
    INTERRUPTED = "interrupted"


class HmiAuthority(str, Enum):
    NONE = "none"
    AUTO = "auto"
    MANUAL = "manual"
    EXTERNAL = "external"
    ADOPTED_MIX = "adopted_mix"
    CONTAINMENT = "containment"


@dataclass(frozen=True)
class OperatorHmiState:
    process_state: HmiProcessState
    authority: HmiAuthority
    title: str
    output_on: bool
    regulator: str
    battery_label: str
    battery_voltage_v: Optional[float]
    current_a: Optional[float]
    power_w: Optional[float]
    battery_temp_c: Optional[float]
    psu_temp_c: Optional[float]
    target_voltage_v: Optional[float]
    current_limit_a: Optional[float]
    progress: str
    safety: str
    attention: str = "normal"
    stage_status: str = ""
    finish_evidence: Optional[Mapping[str, Any]] = None
    stage_time: str = ""
    total_time: str = ""
    delivered_ah: Optional[float] = None


def _finite(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _on(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"on", "true", "1"}


def _regulator(live: Mapping[str, Any]) -> str:
    if _on(live.get("is_cv")):
        return "CV"
    if _on(live.get("is_cc")):
        return "CC"
    return "—"


def _temperature(value: Optional[float]) -> str:
    return "—" if value is None else f"{value:.1f}°C"


def _value(value: Optional[float], digits: int, suffix: str) -> str:
    return "—" if value is None else f"{value:.{digits}f} {suffix}"


def _duration(seconds: Any) -> str:
    value = _finite(seconds)
    if value is None:
        return "—"
    total = max(0, int(value))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}"


def _manual_extrema_status(manual: Any, regulator: str) -> str:
    request = getattr(manual, "request", None)
    if getattr(request, "operation_mode", "") == "main" and regulator == "CV":
        profile = getattr(request, "profile", None)
        required = int(getattr(getattr(profile, "main", None), "confirmation_count", 1) or 1)
        confirmed = int(getattr(manual, "main_min_confirmations", 0) or 0)
        if confirmed < required:
            return "⏳ Imin не подтверждён"
        minimum = _finite(getattr(manual, "_imin", None))
        minimum_text = f"Imin={minimum:.2f} A" if minimum is not None else "Imin=—"
        hold_started = getattr(manual, "main_min_hold_started_at", None)
        if hold_started is None:
            return f"✅ {minimum_text} подтверждён · hold не начат"
        held_m = max(0, int(max(0.0, time.time() - float(hold_started)) // 60))
        hold_hours = _finite(getattr(getattr(profile, "main", None), "hold_hours", None))
        limit_text = f" / {hold_hours:g}ч" if hold_hours is not None else ""
        return f"✅ {minimum_text} подтверждён · hold {held_m // 60}ч {held_m % 60:02d}м{limit_text}"
    if getattr(request, "operation_mode", "") == "mix":
        hold_started = getattr(manual, "finish_hold_started_at", None)
        if hold_started is not None:
            held_s = min(
                MANUAL_MIX_FINISH_HOLD_SEC,
                max(0.0, time.time() - float(hold_started)),
            )
            held_m = int(held_s // 60)
            delta = _finite(getattr(getattr(request, "stop", None), "delta", None))
            if regulator == "CV":
                minimum = _finite(getattr(manual, "_imin", None))
                reference = f"Imin {minimum:.2f}A" if minimum is not None else "Imin —"
                delta_text = f"ΔI {delta:.2f}A" if delta is not None else "ΔI —"
            else:
                maximum = _finite(getattr(manual, "_vmax", None))
                reference = f"Vmax {maximum:.2f}V" if maximum is not None else "Vmax —"
                delta_text = f"ΔV {delta:.2f}V" if delta is not None else "ΔV —"
            return (
                f"✅ {reference} · {delta_text} · "
                f"выдержка {held_m // 60}ч {(held_m % 60):02d}м / 2ч"
            )
    if regulator == "CC":
        maximum = _finite(getattr(manual, "_vmax", None))
        if maximum is not None:
            return f"✅ Vmax: {maximum:.2f} V"
    if regulator == "CV":
        minimum = _finite(getattr(manual, "_imin", None))
        if minimum is not None:
            return f"✅ Imin: {minimum:.2f} A"
    return ""


def _bold_value(value: Optional[float], digits: int, suffix: str) -> str:
    rendered = _value(value, digits, suffix)
    return rendered if rendered == "—" else f"<b>{rendered}</b>"


def _main_mode(state: OperatorHmiState) -> str:
    """Return the operator-facing mode label for the compact panel."""

    if state.process_state is HmiProcessState.STORAGE:
        return "FLOAT"
    if state.regulator in {"CC", "CV"}:
        return state.regulator
    return ""


def _compact_transition(state: OperatorHmiState) -> str:
    """Keep the next transition useful without leaking the legacy status dump."""

    if state.process_state is HmiProcessState.STORAGE:
        return "➡️ Поддержание"
    progress = " ".join(str(state.progress or "").split())
    if not progress:
        return ""
    # Progress may come from the legacy/V2 formatter and already contain
    # Telegram markup.  Normalize it before classifying the transition so the
    # final renderer never escapes trusted tags into visible text.
    plain_progress = html.unescape(re.sub(r"<[^>]*>", "", progress))
    # This is an internal evidence state, not operator-facing copy.  In
    # particular, do not let it leak through the compact panel while CV/CC is
    # still being established.
    if plain_progress == "Режим регулятора определяется":
        return ""
    # Legacy/V2 progress may contain a formatted intent followed by an
    # internal detail (for example ``<b>Обычный заряд</b> Температура: ...``).
    # Keep only the operator-facing intent and build the markup here; passing
    # the original markup through would make the outer renderer escape it.
    for intent in ("Восстановление", "Обычный заряд", "Кондиционирование", "Диагностика"):
        if plain_progress.startswith(intent):
            return f"➡️ <b>{html.escape(intent)}</b>"
    if "Imin" in progress or "I<" in progress:
        return "➡️ FLOAT · Причина: I<0.50A"
    if "Vmax" in progress or "V_max" in progress:
        return "➡️ CV · Причина: Vmax"
    if progress.startswith("Подхват прерван"):
        return "➡️ Подхват прерван · требуется подтверждение"
    # Keep an unexpected application-provided transition bounded on the main panel.
    return f"➡️ {progress[:90]}"


def _compact_stage_label(state: OperatorHmiState) -> str:
    """Build the single operator-facing stage label for line one."""

    if state.process_state is HmiProcessState.STORAGE:
        return "FLOAT"
    title = html.unescape(re.sub(r"<[^>]*>", "", str(state.title or ""))).upper()
    if "MIX" in title or "МИКС" in title:
        return "MIX"
    if "MAIN" in title or "ОСНОВ" in title or "ОБЫЧН" in title or "РУЧНОЙ" in title:
        return "MAIN"
    if "ВОССТАНОВЛЕНИ" in title:
        return "ВОССТАНОВЛЕНИЕ"
    if "КОНДИЦИ" in title:
        return "КОНДИЦИОНИРОВАНИЕ"
    if "ДИАГНОСТ" in title:
        return "ДИАГНОСТИКА"
    if state.process_state is HmiProcessState.PAUSED:
        return "ПАУЗА"
    return "ЗАРЯД"


def _compact_battery_label(label: str) -> str:
    compact = re.sub(r"\s*·\s*", " ", str(label or "").strip())
    return re.sub(r"(\d+(?:\.\d+)?)\s+AH\b", r"\1Ah", compact, flags=re.IGNORECASE)


def _compact_stage_status(state: OperatorHmiState) -> str:
    """Render finish evidence as one compact operator-facing line."""
    if getattr(state, "stage_status", ""):
        stage_status = str(state.stage_status)
        # Vmax is a CC-only finish criterion.  Never expose it while the
        # panel has positively identified the regulator as CV.
        if state.regulator == "CV" and "Vmax" in stage_status:
            return "⏳ Imin не достигнут"
        return stage_status
    progress = html.unescape(re.sub(r"<[^>]*>", "", " ".join(str(state.progress or "").split())))
    if state.regulator == "CV":
        match = re.search(r"Imin\s+([0-9]+(?:\.[0-9]+)?)\s*A.*?после Imin\s+([0-9чм ]+)", progress)
        if match:
            return f"✅ Imin {match.group(1)} A · ⏱ {match.group(2).strip()}"
        if "Imin: ищем" in progress or "Хвост тока ещё не сформирован" in progress or "свежий Imin" in progress:
            return "⏳ Imin не достигнут"
    if state.regulator == "CC":
        match = re.search(r"Vmax\s+([0-9]+(?:\.[0-9]+)?)\s*V.*?после Vmax\s+([0-9чм ]+)", progress)
        if match:
            return f"✅ Vmax {match.group(1)} V · ⏱ {match.group(2).strip()}"
        if "Vmax: ищем" in progress or "свежий Vmax" in progress:
            return "⏳ Vmax не достигнут"
    return ""


def _durable_finish_status(snapshot: Mapping[str, Any], live_mode: str = "") -> Optional[str]:
    hold_active = snapshot.get("finish_hold_started_at") is not None or snapshot.get("delta_reported") is True
    if not hold_active:
        return None
    if "finish_evidence" not in snapshot and "delta_reported" not in snapshot:
        return None
    evidence = snapshot.get("finish_evidence")
    if isinstance(evidence, Mapping) and evidence.get("available") is True:
        mode = str(evidence.get("mode") or "")
        expected_mode = live_mode if live_mode in {"CV", "CC"} else (
            "CV" if snapshot.get("is_cv") else ("CC" if snapshot.get("is_cc") else "")
        )
        reference = _finite(evidence.get("reference_value"))
        delta = _finite(evidence.get("accepted_delta"))
        if mode == expected_mode == "CV" and reference is not None and delta is not None:
            return f"✅ Delta подтверждена · Imin {reference:.2f} A · ΔI {delta:+.2f} A"
        if mode == expected_mode == "CC" and reference is not None and delta is not None:
            return f"✅ Delta подтверждена · Vmax {reference:.2f} V · ΔV {delta:+.2f} V"
    return "✅ Delta подтверждена ранее · Evidence unavailable после восстановления"


def _observer_runtime(app: Any) -> tuple[Any, str]:
    observer = getattr(app, "rd_live_mix_observer", None)
    if observer is None:
        return None, ""
    state = str(getattr(getattr(observer, "state", None), "value", getattr(observer, "state", "")) or "")
    return observer, state


def _manual_is_interrupted(app: Any) -> bool:
    manager = getattr(app, "manual_session_manager", None)
    state = getattr(getattr(manager, "state", None), "value", getattr(manager, "state", ""))
    return str(state or "").strip().lower() == "interrupted"


def _observer_progress(observer: Any, state: str, regulator: str) -> str:
    if state == "off_pending":
        return "Финиш подтверждён · Output OFF ожидает подтверждения"
    if state == "interrupted":
        return "Подхват прерван перезапуском · требуется новое подтверждение"
    hold_started = getattr(observer, "finish_hold_started_at_s", None)
    if hold_started is not None:
        held_s = max(0.0, time.time() - float(hold_started))
        held_m = int(held_s // 60)
        return f"Δ подтверждена · выдержка {held_m // 60}ч {held_m % 60:02d}м / 2ч"
    if regulator == "CV":
        return "Финиш: свежий Imin → ΔI · затем 2ч → OFF"
    if regulator == "CC":
        return "Финиш: свежий Vmax → ΔV · затем 2ч → OFF"
    return "Финишный критерий начнёт считаться после подтверждения режима CV/CC"


def _battery_label_from_observer(observer: Any) -> str:
    battery_id = str(getattr(observer, "battery_id", "") or "").strip()
    chemistry = getattr(observer, "chemistry", None)
    chemistry_text = str(getattr(chemistry, "value", chemistry) or "").strip()
    capacity = _finite(getattr(observer, "capacity_ah", None))
    pieces = [piece for piece in (battery_id, chemistry_text) if piece]
    if capacity is not None and capacity > 0:
        pieces.append(f"{capacity:g} Ah")
    return " · ".join(pieces)


def _normal_safety(live: Mapping[str, Any]) -> tuple[str, str]:
    tripped = []
    if _on(live.get("ovp_triggered")):
        tripped.append("OVP")
    if _on(live.get("ocp_triggered")):
        tripped.append("OCP")
    if tripped:
        return "⚠️ Защита: " + "/".join(tripped), "alarm"
    return "Защита: норма", "normal"


def _operator_telemetry_fresh(live: Mapping[str, Any]) -> bool:
    """Use the bounded freshness contract for truthful presentation."""

    return telemetry_freshness(
        live,
        ("switch", "battery_voltage", "current", "protection_code", "regulation_code"),
    ).valid


def build_operator_hmi_state(app: Any, live: Mapping[str, Any]) -> OperatorHmiState:
    output_on = _on(live.get("switch"))
    telemetry_stale = not _operator_telemetry_fresh(live)
    regulator = "" if telemetry_stale else _regulator(live)
    battery_v = _finite(live.get("battery_voltage"))
    current = _finite(live.get("current"))
    power = _finite(live.get("power"))
    temp_ext = _finite(live.get("temp_ext_v2"))
    if temp_ext is None:
        temp_ext = _finite(live.get("temp_ext"))
    temp_int = _finite(live.get("temp_int_v2"))
    if temp_int is None:
        temp_int = _finite(live.get("temp_int"))
    if temp_int is None:
        temp_int = _finite(live.get("psu_temperature"))
    if temp_int is None:
        temp_int = _finite(live.get("power_supply_temperature"))
    set_v = _finite(live.get("set_voltage"))
    set_i = _finite(live.get("set_current"))
    safety, attention = _normal_safety(live)

    manager = getattr(app, "rd_control_mode_manager", None)
    hands_off = bool(manager is not None and getattr(manager, "hands_off", False))
    observer, observer_state = _observer_runtime(app)
    observer_visible = observer is not None and observer_state in {"active", "off_pending", "interrupted"}

    if observer_visible:
        fingerprint = getattr(observer, "fingerprint", None)
        if fingerprint is not None:
            set_v = _finite(getattr(fingerprint, "set_voltage_v", set_v))
            set_i = _finite(getattr(fingerprint, "set_current_a", set_i))
        process_state = (
            HmiProcessState.INTERRUPTED if observer_state == "interrupted" else HmiProcessState.ADOPTED_MIX
        )
        return OperatorHmiState(
            process_state=process_state,
            authority=HmiAuthority.ADOPTED_MIX,
            title="RD6018 · MIX ПОДХВАЧЕН" if observer_state != "interrupted" else "RD6018 · MIX ТРЕБУЕТ ПОДТВЕРЖДЕНИЯ",
            output_on=output_on,
            regulator=regulator,
            battery_label=_battery_label_from_observer(observer),
            battery_voltage_v=battery_v,
            current_a=current,
            power_w=power,
            battery_temp_c=temp_ext,
            psu_temp_c=temp_int,
            target_voltage_v=set_v,
            current_limit_a=set_i,
            progress=_observer_progress(observer, observer_state, regulator),
            safety=safety,
            attention="warning" if observer_state in {"off_pending", "interrupted"} else attention,
        )

    controller = getattr(app, "charge_controller", None)
    if controller is not None and bool(getattr(controller, "is_active", False)):
        stage = str(getattr(controller, "current_stage", "") or "")
        stage_label = stage
        label_fn = getattr(app, "_stage_label", None)
        if callable(label_fn):
            try:
                stage_label = str(label_fn(stage, short=True))
            except Exception:
                pass
        battery_type = str(getattr(controller, "battery_type", "") or "")
        capacity = _finite(getattr(controller, "ah_capacity", None))
        battery_label = battery_type
        if capacity is not None and capacity > 0:
            battery_label = f"{battery_label} · {capacity:g} Ah" if battery_label else f"{capacity:g} Ah"
        progress = ""
        stage_status = ""
        snapshot: Mapping[str, Any] = {}
        progress_fn = getattr(app, "_format_stage_progress_line", None)
        if callable(progress_fn) and not telemetry_stale:
            try:
                progress = str(progress_fn(dict(live)) or "")
            except Exception:
                progress = ""
        try:
            snapshot = controller.v2_ui_snapshot()
            metrics = dict(snapshot.get("metrics") or {})
            hold_started = snapshot.get("finish_hold_started_at")
            durable_status = _durable_finish_status(snapshot, regulator)
            if durable_status is not None:
                stage_status = durable_status
            elif regulator in {"CV", "CC"} and not bool(
                snapshot.get(
                    "runtime_evidence_available",
                    snapshot.get("runtime_analysis_available", False),
                )
            ):
                stage_status = "⏳ Анализ Imin недоступен" if regulator == "CV" else "⏳ Анализ Vmax недоступен"
            elif regulator == "CV":
                minimum = _finite(metrics.get("current_min_a"))
                if minimum is None or minimum <= 0:
                    stage_status = "⏳ Imin не достигнут"
                else:
                    age = metrics.get("seconds_since_current_min")
                    elapsed = max(0, int(float(age or 0)))
                    if hold_started is not None:
                        elapsed = max(0, int(time.time() - float(hold_started)))
                    stage_status = f"✅ Imin {minimum:.2f} A · ⏱ {elapsed // 3600}ч {(elapsed % 3600) // 60:02d}м"
            elif regulator == "CC":
                maximum = _finite(metrics.get("voltage_max_v"))
                if maximum is None or maximum <= 0:
                    stage_status = "⏳ Vmax не достигнут"
                else:
                    age = metrics.get("seconds_since_voltage_max")
                    elapsed = max(0, int(float(age or 0)))
                    if hold_started is not None:
                        elapsed = max(0, int(time.time() - float(hold_started)))
                    stage_status = f"✅ Vmax {maximum:.2f} V · ⏱ {elapsed // 3600}ч {(elapsed % 3600) // 60:02d}м"
        except Exception:
            stage_status = ""
        if telemetry_stale:
            stage_status = "⚠️ Телеметрия устарела · состояние не подтверждено"
            attention = "warning"
        lowered = stage.lower()
        process = HmiProcessState.RUNNING
        if "safe" in lowered or "cool" in lowered or "ожид" in lowered or "осты" in lowered:
            process = HmiProcessState.PAUSED
        elif "storage" in lowered or "хран" in lowered:
            process = HmiProcessState.STORAGE
        operator_paused = bool(getattr(app, "_operator_pause_active", lambda: False)())
        if operator_paused:
            process = HmiProcessState.PAUSED
        return OperatorHmiState(
            process_state=process,
            authority=HmiAuthority.AUTO,
            title=(
                f"RD6018 · ПАУЗА · {stage_label.upper() if stage_label else 'ЗАРЯД'}"
                if operator_paused
                else f"RD6018 · {stage_label.upper() if stage_label else 'ЗАРЯД'}"
            ),
            output_on=output_on,
            regulator=regulator,
            battery_label=battery_label,
            battery_voltage_v=battery_v,
            current_a=current,
            power_w=power,
            battery_temp_c=temp_ext,
            psu_temp_c=temp_int,
            target_voltage_v=set_v,
            current_limit_a=set_i,
            progress=progress,
            safety=safety,
            attention=attention,
            stage_status=stage_status,
            finish_evidence=(snapshot.get("finish_evidence") if isinstance(snapshot, Mapping) else None),
        )

    manual = getattr(app, "manual_session_manager", None)
    if manual is not None and bool(getattr(manual, "is_active", False)):
        elapsed_s = getattr(manual, "active_elapsed_s", None)
        return OperatorHmiState(
            process_state=HmiProcessState.RUNNING,
            authority=HmiAuthority.MANUAL,
            title=f"RD6018 · {getattr(getattr(manual, 'request', None), 'operation_mode_label', 'Ручной режим')}",
            output_on=output_on,
            regulator=regulator,
            battery_label=str(getattr(manual, "battery_id", "") or ""),
            battery_voltage_v=battery_v,
            current_a=current,
            power_w=power,
            battery_temp_c=temp_ext,
            psu_temp_c=temp_int,
            target_voltage_v=set_v,
            current_limit_a=set_i,
            # This is an internal authority label, not an operator-facing
            # transition. The panel shows the actual stage/evidence instead.
            progress="",
            safety=safety,
            attention=attention,
            stage_status=_manual_extrema_status(manual, regulator),
            stage_time=_duration(elapsed_s),
            total_time=_duration(elapsed_s),
            delivered_ah=_finite(live.get("ah")),
        )

    if _manual_is_interrupted(app):
        return OperatorHmiState(
            process_state=HmiProcessState.IDLE,
            authority=HmiAuthority.NONE,
            title="RD6018 · ПРЕРВАННЫЙ ЗАРЯД",
            output_on=output_on,
            regulator=regulator,
            battery_label=str(getattr(manual, "battery_id", "") or ""),
            battery_voltage_v=battery_v,
            current_a=current,
            power_w=power,
            battery_temp_c=temp_ext,
            psu_temp_c=temp_int,
            target_voltage_v=set_v,
            current_limit_a=set_i,
            progress="Сохранённый заряд требует авторизации или отказа",
            safety=safety,
            attention="warning",
        )

    if hands_off:
        return OperatorHmiState(
            process_state=HmiProcessState.HANDS_OFF,
            authority=HmiAuthority.EXTERNAL,
            title="RD6018 · РУЧНОЕ УПРАВЛЕНИЕ",
            output_on=output_on,
            regulator=regulator,
            battery_label="",
            battery_voltage_v=battery_v,
            current_a=current,
            power_w=power,
            battery_temp_c=temp_ext,
            psu_temp_c=temp_int,
            target_voltage_v=set_v,
            current_limit_a=set_i,
            progress=(
                "Внешняя сессия · автоматика не меняет Output и уставки"
                if output_on
                else "RD свободен от Pb-автоматики"
            ),
            safety=safety,
            attention=attention,
        )

    if output_on:
        return OperatorHmiState(
            process_state=HmiProcessState.CONTAINMENT,
            authority=HmiAuthority.CONTAINMENT,
            title="RD6018 · OUTPUT ВНЕ СЕССИИ",
            output_on=True,
            regulator=regulator,
            battery_label="",
            battery_voltage_v=battery_v,
            current_a=current,
            power_w=power,
            battery_temp_c=temp_ext,
            psu_temp_c=temp_int,
            target_voltage_v=set_v,
            current_limit_a=set_i,
            progress="Нет подтверждённой управляемой сессии",
            safety="⚠️ Требуется проверка ownership",
            attention="alarm",
        )

    return OperatorHmiState(
        process_state=HmiProcessState.IDLE,
        authority=HmiAuthority.NONE,
        title="RD6018 · ГОТОВ",
        output_on=False,
        regulator=regulator,
        battery_label="",
        battery_voltage_v=battery_v,
        current_a=current,
        power_w=power,
        battery_temp_c=temp_ext,
        psu_temp_c=temp_int,
        target_voltage_v=set_v,
        current_limit_a=set_i,
        progress="Готов к новой программе",
        safety=safety,
        attention=attention,
    )


def render_operator_panel(state: OperatorHmiState) -> str:
    mode = _main_mode(state)
    authority_value = getattr(state.authority, "value", state.authority)
    active_panel = authority_value in {
        HmiAuthority.AUTO.value,
        HmiAuthority.MANUAL.value,
        HmiAuthority.ADOPTED_MIX.value,
        HmiAuthority.AUTO,
        HmiAuthority.MANUAL,
        HmiAuthority.ADOPTED_MIX,
    }
    if active_panel:
        stage = _compact_stage_label(state)
        battery = _compact_battery_label(state.battery_label)
        battery_name = str(state.battery_label or "").split("·", 1)[0].strip() or "ЗАРЯД"
        if authority_value == HmiAuthority.MANUAL.value or authority_value == HmiAuthority.MANUAL:
            right_label = f"РУЧНОЙ · {stage or 'MAIN'}"
        else:
            right_label = f"AUTO · {stage or 'ЗАРЯД'}"
        left_label = f"RD6018 · {battery_name} · {mode or stage or '—'}"
        first_line = left_label + (" " * max(4, 42 - len(left_label) - len(right_label))) + right_label
    else:
        first_line = str(state.title or "RD6018")
    lines = [f"<b>{html.escape(first_line)}</b>"]
    if active_panel and battery:
        lines.append(f"🔋 {html.escape(battery)}")
    lines.append(
        f"⚡ {_bold_value(state.battery_voltage_v, 2, 'V')} · "
        f"{_bold_value(state.current_a, 2, 'A')} · 🌡 АКБ "
        f"{_bold_value(state.battery_temp_c, 1, '°C')}"
    )
    if state.target_voltage_v is not None or state.current_limit_a is not None:
        target = _value(state.target_voltage_v, 2, "V")
        limit = _value(state.current_limit_a, 2, "A")
        lines.append(f"🎯 {target} · {limit} 🌡 БП {_temperature(getattr(state, 'psu_temp_c', None))}")
    stage_time = str(getattr(state, "stage_time", "") or "")
    delivered_ah = _finite(getattr(state, "delivered_ah", None))
    time_parts = []
    if stage_time:
        time_parts.append(f"⏱ {html.escape(stage_time)}")
    if delivered_ah is not None:
        time_parts.append(f"⚡ {_value(delivered_ah, 2, 'Ah')}")
    if time_parts:
        lines.append(" · ".join(time_parts))
    stage_status = _compact_stage_status(state)
    transition = _compact_transition(state)
    stage_status_warning = str(getattr(state, "stage_status", ""))
    if stage_status_warning.startswith("⚠️ Телеметрия устарела"):
        lines.append(stage_status_warning)
    else:
        next_line = transition or stage_status
        if transition and stage_status:
            next_line = f"{transition} · {stage_status.removeprefix('➡️ ')}"
        if active_panel and not next_line:
            next_line = "➡️ Ожидание условия перехода"
        if next_line:
            if next_line.startswith("➡️ <b>"):
                lines.append(next_line)
            else:
                lines.append(html.escape(next_line))
    if not active_panel:
        lines.append(f"🛡 {html.escape(state.safety.removeprefix('🛡 ').strip())}")
    return "\n".join(lines)


def _keyboard_from_actions(actions: OperatorActionsView) -> InlineKeyboardMarkup:
    """Render logical capabilities without reading runtime objects."""
    labels = {
        OperatorAction.START_CHARGE: ("⚡ Режимы заряда", "charge_modes"),
        OperatorAction.SELECT_PROFILE: ("🔋 АКБ", "v2_batteries"),
        # Newly rendered panels must use the managed confirmation-based route.
        OperatorAction.STOP_CHARGE: ("🛑 Стоп", "operator_managed_stop"),
        OperatorAction.PAUSE_CHARGE: ("⏸ Пауза", "operator_pause_toggle"),
        OperatorAction.RESUME_CHARGE: ("▶️ Продолжить", "operator_pause_toggle"),
        OperatorAction.SHOW_LOG: ("📋 События", "logs"),
        OperatorAction.SHOW_DIAGNOSTICS: ("ℹ Подробнее", "operator_details"),
        OperatorAction.ACK: ("✅ Подтвердить", "operator_details"),
        OperatorAction.ADOPT_MIX: ("🧲 Подхватить Mix", "rd_live_mix"),
        OperatorAction.STOP_MIX: ("⏹ Остановить Mix", "operator_adopted_stop"),
        OperatorAction.DISABLE_OUTPUT: ("⏹ Output OFF", "rd_hands_off_output_off"),
        OperatorAction.REAUTHORIZE_MANUAL: ("▶ Авторизовать", "v2_manual_reauthorize"),
        OperatorAction.DISCARD_MANUAL: ("🗑 Отказаться", "v2_manual_discard"),
        OperatorAction.RETURN_PB_CONTROL: ("🔒 Вернуть Pb-контроль", "rd_hands_off_disable"),
    }
    rows: list[list[InlineKeyboardButton]] = []
    action_map = {item.action: item for item in actions.available_actions}
    control_actions = [
        action_map.get(OperatorAction.PAUSE_CHARGE),
        action_map.get(OperatorAction.RESUME_CHARGE),
        action_map.get(OperatorAction.STOP_CHARGE),
    ]
    control_buttons = []
    for item in control_actions:
        if item is None:
            continue
        label = labels.get(item.action)
        if label is not None:
            control_buttons.append(InlineKeyboardButton(text=label[0], callback_data=label[1]))
    if control_buttons:
        rows.append(control_buttons)
    handled = {
        OperatorAction.PAUSE_CHARGE,
        OperatorAction.RESUME_CHARGE,
        OperatorAction.STOP_CHARGE,
        OperatorAction.SHOW_GRAPH,
    }
    secondary = {OperatorAction.SHOW_LOG, OperatorAction.SHOW_DIAGNOSTICS}
    for item in actions.available_actions:
        if item.action in handled or item.action in secondary:
            continue
        label = labels.get(item.action)
        if label is not None:
            rows.append([InlineKeyboardButton(text=label[0], callback_data=label[1])])
    for item in actions.available_actions:
        if item.action not in secondary:
            continue
        label = labels.get(item.action)
        if label is not None:
            rows.append([InlineKeyboardButton(text=label[0], callback_data=label[1])])
    rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="operator_refresh")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_operator_keyboard(
    app: Any,
    state: OperatorHmiState,
    *,
    actions: OperatorActionsView | None = None,
) -> InlineKeyboardMarkup:
    """Authoritative L2 operator keyboard.

    Other builders remain compatibility surfaces for legacy handlers, but the
    installed production panel always routes through this builder.
    """
    if actions is not None:
        return _keyboard_from_actions(actions)

    # Compatibility callers may omit the application action view.  Derive a
    # conservative, data-only view from the already-built HMI state instead of
    # reading controller/session objects from the presentation layer.
    if state.process_state is HmiProcessState.IDLE:
        if "авторизац" in str(state.progress or "").lower():
            return InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="▶ Авторизовать", callback_data="v2_manual_reauthorize"),
                    InlineKeyboardButton(text="🗑 Отказаться", callback_data="v2_manual_discard"),
                ],
                [InlineKeyboardButton(text="🔄 Обновить", callback_data="operator_refresh")],
            ])
        else:
            fallback = OperatorActionsView.for_state("IDLE", safety_allowed=True)
    elif state.process_state is HmiProcessState.STORAGE:
        fallback = OperatorActionsView(tuple(OperatorActionSpec(action) for action in (
            OperatorAction.SHOW_LOG,
            OperatorAction.SHOW_DIAGNOSTICS,
        )))
    elif state.process_state is HmiProcessState.PAUSED:
        fallback = OperatorActionsView(
            tuple(OperatorActionSpec(action) for action in (
                OperatorAction.RESUME_CHARGE,
                OperatorAction.STOP_CHARGE,
                OperatorAction.SHOW_LOG,
                OperatorAction.SHOW_GRAPH,
                OperatorAction.SHOW_DIAGNOSTICS,
            )),
        )
    elif state.authority in {HmiAuthority.AUTO, HmiAuthority.MANUAL}:
        fallback = OperatorActionsView(
            tuple(OperatorActionSpec(action) for action in (
                OperatorAction.PAUSE_CHARGE,
                OperatorAction.STOP_CHARGE,
                OperatorAction.SHOW_LOG,
                OperatorAction.SHOW_GRAPH,
                OperatorAction.SHOW_DIAGNOSTICS,
            )),
        )
    elif state.process_state is HmiProcessState.HANDS_OFF:
        actions = (
            (OperatorAction.ADOPT_MIX, OperatorAction.DISABLE_OUTPUT)
            if state.output_on
            else (OperatorAction.SELECT_PROFILE, OperatorAction.SHOW_DIAGNOSTICS)
        )
        fallback = OperatorActionsView(tuple(OperatorActionSpec(action) for action in actions))
    elif state.process_state is HmiProcessState.ADOPTED_MIX:
        fallback = OperatorActionsView(tuple(OperatorActionSpec(action) for action in (
            OperatorAction.STOP_MIX, OperatorAction.SHOW_LOG, OperatorAction.SHOW_DIAGNOSTICS,
        )))
    elif state.process_state is HmiProcessState.INTERRUPTED:
        fallback = OperatorActionsView(tuple(OperatorActionSpec(action) for action in (
            OperatorAction.ADOPT_MIX, OperatorAction.SHOW_LOG, OperatorAction.SHOW_DIAGNOSTICS,
        )))
    else:
        fallback = OperatorActionsView(tuple(OperatorActionSpec(action) for action in (
            OperatorAction.SHOW_LOG, OperatorAction.SHOW_DIAGNOSTICS,
        )))
    return _keyboard_from_actions(fallback)


def render_operator_details(app: Any, state: OperatorHmiState, live: Mapping[str, Any]) -> str:
    lines = ["<b>📋 Информация для оператора</b>", ""]
    ah = _finite(live.get("ah"))
    uptime = str(live.get("uptime") or "—")
    input_voltage = _finite(live.get("input_voltage"))
    if state.process_state in {HmiProcessState.ADOPTED_MIX, HmiProcessState.INTERRUPTED}:
        observer, observer_state = _observer_runtime(app)
        lines.extend(
            [
                f"Сессия: <b>{'Mix подхвачен' if observer_state != 'interrupted' else 'подхват прерван'}</b>",
                f"АКБ: {html.escape(state.battery_label or '—')}",
                f"Output: {'ON' if state.output_on else 'OFF'} · {html.escape(state.regulator)}",
                f"Уставки прибора: {_value(state.target_voltage_v, 2, 'V')} / {_value(state.current_limit_a, 2, 'A')}",
                f"Состояние наблюдателя: <code>{html.escape(observer_state or '—')}</code>",
                "",
                "Бот не переписывал текущие V/I/OVP/OCP при подхвате. История HA — только контекст; "
                "финишное Delta-доказательство считается заново после подтверждения.",
                "",
                "Низкоуровневая граница RD остаётся HANDS_OFF: текущий deployed ESPHome ещё не имеет "
                "валидированного live-adopt handshake для PB_MANAGED. Для этой сессии бот владеет только "
                "Delta-наблюдением и, если выбран соответствующий режим, verified Output OFF.",
            ]
        )
        if observer is not None:
            status = str(getattr(observer, "last_status", "") or "")
            if status:
                lines.append(f"\nПоследнее: <code>{html.escape(status)}</code>")
    else:
        lines.extend(
            [
                f"Состояние: <b>{html.escape(state.process_state.value)}</b> · "
                f"Authority: <code>{html.escape(state.authority.value)}</code>",
                f"Output: <b>{'ON' if state.output_on else 'OFF'}</b> · режим {html.escape(state.regulator)}",
                f"⚡ {_value(state.battery_voltage_v, 3, 'V')} · {_value(state.current_a, 3, 'A')}",
                f"🌡 АКБ: {_temperature(state.battery_temp_c)} · БП: {_temperature(state.psu_temp_c)}",
            ]
        )
        controller = getattr(app, "charge_controller", None)
        if controller is not None and bool(getattr(controller, "is_active", False)):
            try:
                timers = controller.get_timers()
            except Exception:
                timers = {}
            stage = str(getattr(controller, "current_stage", "") or "—")
            battery_type = str(getattr(controller, "battery_type", "") or "—")
            capacity = _finite(getattr(controller, "ah_capacity", None))
            lines.extend(
                [
                    "",
                    "🧠 <b>Статистика по этапу</b>",
                    f"📍 Этап: <b>{html.escape(stage)}</b>",
                    f"🔋 АКБ: {html.escape(battery_type)} · {capacity:g} Ah" if capacity else f"🔋 АКБ: {html.escape(battery_type)}",
                    f"⏱ Этап: {html.escape(str(timers.get('stage_time', '—')))} · всего {html.escape(str(timers.get('total_time', '—')))}",
                    f"⌛ Лимит: {html.escape(str(timers.get('remaining_time', '—')))}",
                    f"📦 Набрано: {_value(ah, 2, 'Ah')}",
                ]
            )
            if state.progress:
                progress = html.unescape(re.sub(r"<[^>]*>", "", " ".join(str(state.progress).split())))
                lines.append(f"🎯 Финиш: {html.escape(progress)}")
        else:
            manual = getattr(app, "manual_session_manager", None)
            if manual is not None and bool(getattr(manual, "is_active", False)):
                request = getattr(manual, "request", None)
                elapsed = _duration(getattr(manual, "active_elapsed_s", None))
                limit = getattr(getattr(request, "stop", None), "max_active_seconds", None)
                remaining = "—"
                if _finite(limit) is not None and _finite(getattr(manual, "active_elapsed_s", None)) is not None:
                    remaining = _duration(max(0.0, float(limit) - float(manual.active_elapsed_s)))
                capacity = _finite(getattr(request, "capacity_ah", None)) if request is not None else None
                lines.extend(
                    [
                        "",
                        "🧠 <b>Статистика ручного заряда</b>",
                        f"📍 Этап: <b>Ручной режим</b>",
                        f"⏱ Этап: {elapsed} · всего {elapsed}",
                        f"⌛ Лимит: {remaining}",
                        f"📦 Отдано: {_value(ah, 2, 'Ah')}",
                        f"🔋 Заданная ёмкость: {_value(capacity, 2, 'Ah')}",
                    ]
                )
        lines.extend(
            [
                f"🎯 Уставки: {_value(state.target_voltage_v, 2, 'V')} · лимит {_value(state.current_limit_a, 2, 'A')}",
                f"🔌 Вход: {_value(input_voltage, 1, 'V')} · ⏱ Работа: {html.escape(uptime)}",
            ]
        )
    lines.append(f"🛡 Защита: {html.escape(state.safety)}")
    return "\n".join(lines)


def render_operator_details_view(view: OperatorDetailsView) -> str:
    """Render a read-only DTO without accessing runtime objects."""
    lines = ["<b>📋 Информация для оператора</b>", ""]
    if view.observer_state in {"active", "off_pending", "interrupted"}:
        lines.extend([
            f"Сессия: <b>{'Mix подхвачен' if view.observer_state != 'interrupted' else 'подхват прерван'}</b>",
            f"АКБ: {html.escape(view.battery_label or '—')}",
            f"Output: {'ON' if view.output_on else 'OFF'} · {html.escape(view.regulator)}",
            f"Уставки прибора: {_value(view.target_voltage_v, 2, 'V')} / {_value(view.current_limit_a, 2, 'A')}",
            f"Состояние наблюдателя: <code>{html.escape(view.observer_state or '—')}</code>",
        ])
        if view.observer_status:
            lines.append(f"\nПоследнее: <code>{html.escape(view.observer_status)}</code>")
    else:
        lines.extend([
            f"Состояние: <b>{html.escape(view.process_state)}</b> · Authority: <code>{html.escape(view.authority)}</code>",
            f"Output: <b>{'ON' if view.output_on else 'OFF'}</b> · режим {html.escape(view.regulator)}",
            f"⚡ {_value(view.battery_voltage_v, 3, 'V')} · {_value(view.current_a, 3, 'A')}",
            f"🌡 АКБ: {_temperature(view.battery_temp_c)} · БП: {_temperature(view.psu_temp_c)}",
        ])
        if view.stage or view.battery_type:
            lines.extend([
                "", "🧠 <b>Статистика по этапу</b>",
                f"📍 Этап: <b>{html.escape(view.stage or '—')}</b>",
                f"🔋 АКБ: {html.escape(view.battery_type or view.battery_label or '—')}" + (f" · {view.capacity_ah:g} Ah" if view.capacity_ah else ""),
                f"⏱ Этап: {html.escape(view.stage_time)} · всего {html.escape(view.total_time)}",
                f"⌛ Лимит: {html.escape(view.remaining_time)}",
                f"📦 Набрано: {_value(view.delivered_ah, 2, 'Ah')}",
            ])
        elif view.manual_capacity_ah is not None:
            lines.extend(["", "🧠 <b>Статистика ручного заряда</b>", f"🔋 Заданная ёмкость: {_value(view.manual_capacity_ah, 2, 'Ah')}"])
        lines.extend([
            f"🎯 Уставки: {_value(view.target_voltage_v, 2, 'V')} · лимит {_value(view.current_limit_a, 2, 'A')}",
            f"🔌 Вход: {_value(view.input_voltage_v, 1, 'V')} · ⏱ Работа: {html.escape(view.uptime)}",
        ])
    lines.append(f"🛡 Защита: {html.escape(view.safety)}")
    return "\n".join(lines)


def render_operator_service_details(app: Any, state: OperatorHmiState, live: Mapping[str, Any]) -> str:
    """Technical read-only details kept outside the operator screen."""
    lines = ["<b>🛠 Сервисная информация</b>", ""]
    lines.append(f"Authority: <code>{html.escape(state.authority.value)}</code>")
    lines.append(f"Output: <code>{'ON' if state.output_on else 'OFF'}</code>")
    lines.append(f"Режим: <code>{html.escape(state.regulator or '—')}</code>")
    controller = getattr(app, "charge_controller", None)
    if controller is not None:
        try:
            snapshot = controller.v2_ui_snapshot()
        except Exception:
            snapshot = {}
        lines.append(f"Этап: <code>{html.escape(str(getattr(controller, 'current_stage', '—')))}</code>")
        lines.append(f"V2 analysis: <code>{'available' if snapshot.get('runtime_analysis_available') else 'unavailable'}</code>")
        lines.append(f"Decision: <code>{html.escape(str(snapshot.get('decision') or '—'))}</code>")
    ovp = _finite(live.get("ovp"))
    ocp = _finite(live.get("ocp"))
    protection = html.escape(str(live.get("protection_code") or "—"))
    regulation = html.escape(str(live.get("regulation_code") or "—"))
    lines.extend(
        [
            f"OVP/OCP: <code>{_value(ovp, 2, 'V')} / {_value(ocp, 2, 'A')}</code>",
            f"Protection/Regulation: <code>{protection} / {regulation}</code>",
            f"Heartbeat: <code>{html.escape(str(live.get('last_reported') or live.get('last_updated') or '—'))}</code>",
            "Lease/Modbus details доступны в диагностическом экране.",
        ]
    )
    return "\n".join(lines)


def render_operator_service_details_view(view: ServiceDetailsView) -> str:
    lines = ["<b>🛠 Сервисная информация</b>", ""]
    lines.extend([
        f"Authority: <code>{html.escape(view.authority)}</code>",
        f"Output: <code>{'ON' if view.output_on else 'OFF'}</code>",
        f"Режим: <code>{html.escape(view.regulator or '—')}</code>",
        f"Этап: <code>{html.escape(view.stage)}</code>",
        f"V2 analysis: <code>{view.v2_analysis}</code>",
        f"Decision: <code>{html.escape(view.decision)}</code>",
        f"OVP/OCP: <code>{_value(view.ovp_v, 2, 'V')} / {_value(view.ocp_a, 2, 'A')}</code>",
        f"Protection/Regulation: <code>{html.escape(view.protection)} / {html.escape(view.regulation)}</code>",
        f"Heartbeat: <code>{html.escape(view.heartbeat)}</code>",
        "Lease/Modbus details доступны в диагностическом экране.",
    ])
    return "\n".join(lines)


def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅ К панели", callback_data="operator_done")]]
    )


def _graph_keyboard(app: Any, user_id: int) -> InlineKeyboardMarkup:
    selected = str(app._chart_range_for_user(user_id))

    def button(mode: str, text: str) -> InlineKeyboardButton:
        marker = "● " if selected == mode else ""
        return InlineKeyboardButton(text=f"{marker}{text}", callback_data=f"operator_graph_{mode}")

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                button(app.CHART_RANGE_30M, "30м"),
                button(app.CHART_RANGE_2H, "2ч"),
                button(app.CHART_RANGE_SESSION, "Сессия"),
            ],
            [InlineKeyboardButton(text="⬅ К панели", callback_data="operator_done")],
        ]
    )


async def _render_graph_workspace(app: Any, call: Any, user_id: int) -> None:
    _chart_mode, graph_since, limit_pts = app._chart_query_params(user_id)
    times, voltages, currents, temps = await app.get_graph_data_with_temp(
        limit=limit_pts,
        since_timestamp=graph_since,
    )
    buf = await asyncio.to_thread(app.generate_chart, times, voltages, currents, temps)
    markup = _graph_keyboard(app, user_id)
    if buf:
        photo = app.BufferedInputFile(buf.getvalue(), filename="rd6018-graph.png")
        await call.message.answer_photo(
            photo,
            caption="<b>График RD6018</b>",
            parse_mode=app.ParseMode.HTML,
            reply_markup=markup,
        )
    else:
        await call.message.answer(
            "<b>График RD6018</b>\n\nНедостаточно данных.",
            parse_mode=app.ParseMode.HTML,
            reply_markup=markup,
        )


def _more_keyboard(state: OperatorHmiState) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="🧠 AI анализ", callback_data="ai_analysis")]]
    if state.process_state is HmiProcessState.IDLE:
        rows.append([InlineKeyboardButton(text="🛠 Ручной режим", callback_data="v2_manual_choose")])
        rows.append([InlineKeyboardButton(text="🔋 АКБ", callback_data="v2_batteries")])
    if state.process_state is HmiProcessState.ADOPTED_MIX:
        rows.append([InlineKeyboardButton(text="🧲 Статус Mix", callback_data="rd_live_mix_status")])
    if state.process_state is HmiProcessState.HANDS_OFF and not state.output_on:
        rows.append([InlineKeyboardButton(text="🔒 Вернуть Pb-контроль", callback_data="rd_hands_off_disable")])
    rows.append([InlineKeyboardButton(text="⬅ К панели", callback_data="operator_done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def install_operator_hmi(app: Any) -> None:
    """Install the final semantic L2 panel after all ownership/UI wrappers.

    This renderer intentionally supersedes the graph-heavy legacy dashboard. It does
    not change control authority: an externally adopted Mix remains low-level
    HANDS_OFF until a separately validated edge live-adoption contract exists.
    """
    if bool(getattr(app, "_operator_hmi_installed", False)):
        return

    async def route_read_intent(call: Any, kind: OperatorIntentKind) -> bool:
        interface = getattr(app, "operator_interface", None)
        submit = getattr(interface, "submit_intent", None)
        if not callable(submit):
            return True
        user = str(getattr(getattr(call, "from_user", None), "id", "0"))
        result = await submit(OperatorIntent(kind=kind, source="telegram", user=user))
        if getattr(result, "status", None) == "rejected":
            await call.answer("Действие пока не маршрутизировано", show_alert=True)
            return False
        return True

    async def build_and_send_dashboard(
        chat_id: int,
        user_id: int,
        old_msg_id: Optional[int] = None,
        anchor_msg_id: Optional[int] = None,
    ) -> int:
        interface = getattr(app, "operator_interface", None)
        if interface is None:
            raise RuntimeError("operator interface is not installed")
        snapshot = await interface.get_operator_snapshot()
        actions = await interface.get_operator_actions()
        from application.operator_snapshot_provider import OperatorSnapshotProvider
        state = OperatorSnapshotProvider.hmi_state_from_snapshot(snapshot)
        text = render_operator_panel(state)
        markup = build_operator_keyboard(app, state, actions=actions)
        target = old_msg_id or anchor_msg_id
        if target:
            try:
                await app.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=target,
                    text=text,
                    reply_markup=markup,
                    parse_mode=app.ParseMode.HTML,
                )
                app.user_dashboard[user_id] = target
                app.chat_dashboard[chat_id] = target
                return int(target)
            except Exception as exc:
                if "message is not modified" in str(exc).lower():
                    app.user_dashboard[user_id] = target
                    app.chat_dashboard[chat_id] = target
                    return int(target)
                try:
                    await app.bot.delete_message(chat_id, target)
                except Exception:
                    pass
        sent = await app.bot.send_message(
            chat_id,
            text,
            reply_markup=markup,
            parse_mode=app.ParseMode.HTML,
        )
        app.user_dashboard[user_id] = sent.message_id
        app.chat_dashboard[chat_id] = sent.message_id
        return int(sent.message_id)

    app._build_and_send_dashboard = build_and_send_dashboard

    def compact_dashboard_caption(live: Mapping[str, Any], chart_mode: str, mode: str, idle_warning: str) -> str:
        del chart_mode, mode, idle_warning
        return render_operator_panel(build_operator_hmi_state(app, live))

    app._compact_dashboard_caption = compact_dashboard_caption

    def dashboard_keyboard(is_on: bool, user_id: int, *, back_to_dashboard: bool = False) -> InlineKeyboardMarkup:
        if back_to_dashboard:
            return _back_keyboard()
        # Keyboard rendering itself has no live dict. Build a conservative state from
        # the known ownership/session facts; normal dashboard rendering uses full live.
        observer, observer_state = _observer_runtime(app)
        manager = getattr(app, "rd_control_mode_manager", None)
        if observer is not None and observer_state in {"active", "off_pending", "interrupted"}:
            state = OperatorHmiState(
                HmiProcessState.INTERRUPTED if observer_state == "interrupted" else HmiProcessState.ADOPTED_MIX,
                HmiAuthority.ADOPTED_MIX,
                "",
                bool(is_on),
                "—",
                _battery_label_from_observer(observer),
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                "",
                "",
            )
        elif manager is not None and bool(getattr(manager, "hands_off", False)):
            state = OperatorHmiState(HmiProcessState.HANDS_OFF, HmiAuthority.EXTERNAL, "", bool(is_on), "—", "", None, None, None, None, None, None, None, "", "")
        elif bool(getattr(app.charge_controller, "is_active", False)):
            state = OperatorHmiState(HmiProcessState.RUNNING, HmiAuthority.AUTO, "", bool(is_on), "—", "", None, None, None, None, None, None, None, "", "")
        elif getattr(app, "manual_session_manager", None) is not None and bool(getattr(app.manual_session_manager, "is_active", False)):
            state = OperatorHmiState(HmiProcessState.RUNNING, HmiAuthority.MANUAL, "", bool(is_on), "—", "", None, None, None, None, None, None, None, "", "")
        else:
            state = OperatorHmiState(HmiProcessState.IDLE if not is_on else HmiProcessState.CONTAINMENT, HmiAuthority.NONE if not is_on else HmiAuthority.CONTAINMENT, "", bool(is_on), "—", "", None, None, None, None, None, None, None, "", "")
        return build_operator_keyboard(app, state)

    app._build_dashboard_keyboard = dashboard_keyboard

    @app.router.callback_query(F.data == "operator_details")
    async def _operator_details(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        if not await route_read_intent(call, OperatorIntentKind.SHOW_DIAGNOSTICS):
            return
        interface = getattr(app, "operator_interface", None)
        if interface is None:
            await call.answer("Интерфейс чтения недоступен", show_alert=True)
            return
        details = await interface.get_operator_details()
        await call.answer()
        await call.message.answer(
            render_operator_details_view(details),
            parse_mode=app.ParseMode.HTML,
            reply_markup=_back_keyboard(),
        )

    @app.router.callback_query(F.data == "operator_service_details")
    async def _operator_service_details(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        if not await route_read_intent(call, OperatorIntentKind.SHOW_DIAGNOSTICS):
            return
        interface = getattr(app, "operator_interface", None)
        if interface is None:
            await call.answer("Интерфейс чтения недоступен", show_alert=True)
            return
        details = await interface.get_service_details()
        await call.answer()
        await call.message.answer(
            render_operator_service_details_view(details),
            parse_mode=app.ParseMode.HTML,
            reply_markup=_back_keyboard(),
        )

    @app.router.callback_query(F.data == "operator_pause_toggle")
    async def _operator_pause_toggle_handler(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        interface = getattr(app, "operator_interface", None)
        submit = getattr(interface, "submit_intent", None)
        if callable(submit):
            user = str(getattr(getattr(call, "from_user", None), "id", "0"))
            kind = (
                OperatorIntentKind.RESUME_CHARGE
                if bool(getattr(app, "_operator_pause_active", lambda: False)())
                else OperatorIntentKind.PAUSE_CHARGE
            )
            result = await submit(OperatorIntent(kind=kind, source="telegram", user=user))
            if getattr(result, "status", None) == "rejected":
                await call.answer("Пауза пока недоступна", show_alert=True)
                return
        handler = getattr(app, "_operator_pause_toggle", None)
        if handler is None:
            await call.answer("Пауза недоступна", show_alert=True)
            return
        # A managed pause may outlive Telegram's callback-query answer window.
        # A late acknowledgement must not be reported as a failed pause.
        try:
            await call.answer()
        except Exception:
            pass
        try:
            await handler(call)
        except Exception as exc:
            app.logger.exception("operator pause failed: %s", exc)
            return
        user_id = call.from_user.id if call.from_user else 0
        refresh = getattr(app, "_refresh_operator_panel", None)
        if refresh is not None:
            await refresh(call.message.chat.id, user_id, call.message.message_id)

    @app.router.callback_query(F.data == "operator_graph")
    async def _operator_graph(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        if not await route_read_intent(call, OperatorIntentKind.SHOW_GRAPH):
            return
        await call.answer()
        user_id = call.from_user.id if call.from_user else 0
        await _render_graph_workspace(app, call, user_id)

    @app.router.callback_query(F.data == "operator_refresh")
    async def _operator_refresh(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        if not await route_read_intent(call, OperatorIntentKind.REFRESH_PANEL):
            return
        await call.answer("Обновляю")
        user_id = call.from_user.id if call.from_user else 0
        refresh = getattr(app, "_refresh_operator_panel", None)
        if refresh is not None:
            await refresh(call.message.chat.id, user_id, call.message.message_id)
        else:
            await app._build_and_send_dashboard(
                call.message.chat.id,
                user_id,
                old_msg_id=call.message.message_id,
            )

    @app.router.callback_query(F.data.startswith("operator_graph_"))
    async def _operator_graph_range(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        raw = str(call.data).removeprefix("operator_graph_")
        if raw not in app.CHART_RANGE_VALUES:
            await call.answer("Неизвестный диапазон", show_alert=True)
            return
        user_id = call.from_user.id if call.from_user else 0
        app.user_chart_range[user_id] = raw
        await call.answer()
        await _render_graph_workspace(app, call, user_id)

    @app.router.callback_query(F.data == "operator_more")
    async def _operator_more(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        if not await route_read_intent(call, OperatorIntentKind.SHOW_DIAGNOSTICS):
            return
        interface = getattr(app, "operator_interface", None)
        if interface is None:
            await call.answer("Интерфейс чтения недоступен", show_alert=True)
            return
        snapshot = await interface.get_operator_snapshot()
        from application.operator_snapshot_provider import OperatorSnapshotProvider
        state = OperatorSnapshotProvider.hmi_state_from_snapshot(snapshot)
        await call.answer()
        await call.message.answer(
            "<b>Ещё</b>\n\nСервисные и диагностические экраны.",
            parse_mode=app.ParseMode.HTML,
            reply_markup=_more_keyboard(state),
        )

    @app.router.callback_query(F.data == "operator_adopted_stop")
    async def _operator_adopted_stop(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        observer, state = _observer_runtime(app)
        if observer is None or state not in {"active", "off_pending"}:
            await call.answer("Подхваченная Mix уже не активна", show_alert=True)
            return
        await call.answer()
        await call.message.answer(
            "<b>Остановить текущий Mix?</b>\n\nБудет выполнен только verified Output OFF. Уставки RD не изменяются.",
            parse_mode=app.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="⏹ ОСТАНОВИТЬ", callback_data="operator_adopted_stop_execute")],
                    [InlineKeyboardButton(text="Продолжить Mix", callback_data="operator_done")],
                ]
            ),
        )

    @app.router.callback_query(F.data == "operator_adopted_stop_execute")
    async def _operator_adopted_stop_execute(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        manager = getattr(app, "rd_control_mode_manager", None)
        if manager is None or not bool(getattr(manager, "hands_off", False)):
            await call.answer("Verified HANDS_OFF OFF недоступен", show_alert=True)
            return
        await call.answer()
        try:
            await manager.operator_output_off(app.ENTITY_MAP.get("switch"))
            observer = getattr(app, "rd_live_mix_observer", None)
            if observer is not None:
                await observer.observe_once()
        except Exception as exc:
            await call.answer(str(exc), show_alert=True)
            return
        await call.message.answer("⏹ Mix остановлен. Output подтверждён OFF.")

    app._operator_hmi_installed = True
