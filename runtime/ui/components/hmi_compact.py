"""Compact operator panel text projections; no session/charger authority."""
from __future__ import annotations
import html
import re
from typing import Any, Mapping, Optional
from .hmi_state import HmiProcessState, HmiAuthority, OperatorHmiState
from .hmi_values import _finite, _value
from runtime.ui.hmi_layout_config import COMPACT_TRANSITION_MAX_CHARS

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
    return f"➡️ {progress[:COMPACT_TRANSITION_MAX_CHARS]}"


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
