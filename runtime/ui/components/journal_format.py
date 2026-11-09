"""Read-only human formatting of persisted charge journal rows."""

from __future__ import annotations
import html
import re
from typing import Iterable
from .journal_filter import _parts, operator_journal_events
from runtime.ui.journal_config import (JOURNAL_DEFAULT_SHOWN, JOURNAL_TIME_CHARS, JOURNAL_RAW_HTML_MAX, JOURNAL_STAGE_HTML_MAX, JOURNAL_SUMMARY_HTML_MAX)
from runtime.ui.labels.journal import JOURNAL_STAGE_NAMES, JOURNAL_MILESTONE_LABELS, MAIN_MINIMUM_PREFIXES

def _stage_name(stage: str) -> str:
    stage = stage.strip()
    names = JOURNAL_STAGE_NAMES
    return names.get(stage, stage or "Заряд")


def _measurements(v: str, i: str, temp: str) -> str:
    values = []
    if v.strip() and v.strip() != "—":
        values.append(f"U {v.strip()}")
    if i.strip() and i.strip() != "—":
        values.append(f"I {i.strip()}")
    if temp.strip() and temp.strip() != "—":
        values.append(f"T {temp.strip()}")
    return " · ".join(values)


def _escape_limited(value: str, limit: int) -> str:
    """HTML-escape without letting hostile text expand a Telegram page."""
    marker = "… [запись сокращена]"
    chunks: list[str] = []
    used = 0
    for char in value:
        escaped = html.escape(char)
        if used + len(escaped) > limit - len(marker):
            chunks.append(marker)
            break
        chunks.append(escaped)
        used += len(escaped)
    return "".join(chunks)


def format_journal_event(event_line: str) -> str:
    """Render one persisted row as one concise Russian Telegram line."""
    try:
        if len(event_line.split(" | ", 6)) < 7:
            return f"<code>{_escape_limited(event_line, JOURNAL_RAW_HTML_MAX)}</code>"
        ts, stage_raw, v, i, temp, _ah, event = _parts(event_line)
        timestamp = ts.strip().strip("[]")
        clock = timestamp.split(" ")[-1][:JOURNAL_TIME_CHARS] if timestamp else "—"
        stage = _stage_name(stage_raw)
        raw = event.strip()
        name, _, detail = raw.partition(" | ")
        upper = name.upper()
        metrics = _measurements(v, i, temp)

        if name == "SESSION_STOP":
            reason = "Остановлен оператором; Output OFF подтверждён" if "verified_off" in raw else "Заряд остановлен"
            summary, icon = reason, "🛑"
        elif name == "START" or name.startswith("START |"):
            profile = re.search(r"profile=([^|]+)", raw, re.I)
            summary = "Заряд запущен" + (f" · АКБ {profile.group(1).strip()}" if profile else "")
            icon = "🏁"
        elif name.startswith("SESSION_"):
            profile = re.search(r"(?:^|\|\s*)profile=([^|]+)", raw, re.I)
            capacity = re.search(r"(?:^|\|\s*)capacity_ah=([^|]+)", raw, re.I)
            label = "Заряд запущен" if name == "SESSION_START" else "Событие сессии"
            extras = [x.strip() for x in (
                f"АКБ {profile.group(1).strip()}" if profile else "",
                f"ёмкость {capacity.group(1).strip()} А·ч" if capacity else "",
            ) if x]
            summary = label + (" · " + " · ".join(extras) if extras else "")
            icon = "🏁"
        elif name == "STAGE_CHANGE":
            transition = detail.strip() or raw.partition(" ")[2].strip()
            # The stage field is the new stage, while detail records both ends.
            summary, icon = f"Переход этапа: {transition}", "➡️"
        elif name == "MIX_STARTED":
            reason_match = re.search(r"(?:^|\|\s*)reason=([^|]+)", raw, re.I)
            voltage_match = re.search(r"(?:^|\|\s*)target_voltage_v=([0-9]+(?:[.,][0-9]+)?)", raw, re.I)
            current_match = re.search(r"(?:^|\|\s*)target_current_a=([0-9]+(?:[.,][0-9]+)?)", raw, re.I)
            reason = reason_match.group(1).strip().replace("_", " ") if reason_match else ""
            target = ""
            if voltage_match and current_match:
                target = (
                    f" · цель {voltage_match.group(1).replace('.', ',')} В"
                    f" / {current_match.group(1).replace('.', ',')} А"
                )
            summary = "Начат MIX" + (f" · причина: {reason}" if reason else "") + target
            icon = "🚀"
        elif name.startswith("END"):
            summary, icon = "Этап завершён", "✅"
            fields = [x.strip() for x in raw.partition("|")[2].split(" | ") if x.strip()]
            useful = [x for x in fields if not x.lower().startswith(("время:", "ёмкость:", "t:", "v:", "i:"))]
            if useful:
                summary += " · " + "; ".join(useful)
        elif upper.startswith(("WARNING", "TEMP", "TEMPERATURE")):
            summary, icon = f"Предупреждение: {name.removeprefix('WARNING_').replace('_', ' ').lower()}", "⚠️"
        elif upper.startswith("BANK_FAULT_"):
            summary, icon = f"Обнаружена неисправность банки АКБ ({name.removeprefix('BANK_FAULT_')})", "⚠️"
        elif "STOP" in upper or "TRIP" in upper or "EMERGENCY" in upper or upper in {"OVP_TRIGGERED", "OCP_TRIGGERED"}:
            labels = {"OVP_TRIGGERED": "Сработала защита по перенапряжению", "OCP_TRIGGERED": "Сработала защита по току", "MANUAL_OFF": "Заряд остановлен вручную"}
            summary, icon = labels.get(name, f"Остановка или авария: {name.replace('_', ' ').lower()}"), "🛑"
        elif upper.startswith("V2_FINISH_HOLD_START"):
            summary, icon = "Delta подтверждён; началась финишная выдержка", "⏱️"
            if detail:
                summary += f" · {detail.strip()}"
        elif upper.startswith("V2_COOLING_FAIL_CLOSED"):
            summary, icon = "Аварийно остановлено: ошибка охлаждения", "🛑"
        elif name in MAIN_MINIMUM_PREFIXES:
            # Historic row has Imin, not a current countdown or next-stage authority.
            match = re.search(r"Imin=([0-9]+(?:[.,][0-9]+)?)A\b", detail)
            value = match.group(1).replace(".", ",").rstrip("0").rstrip(",") if match else None
            summary = (f"{MAIN_MINIMUM_PREFIXES[name]}={value}?"
                       if value is not None else MAIN_MINIMUM_PREFIXES[name])
            icon = "?"
        elif upper.startswith(("MAIN_HOLD", "MIX", "DELTA", "I_MIN", "IMIN", "V_MAX", "VMAX", "STABIL")):
            # Only report facts that were actually written to charging_history.log.
            labels = JOURNAL_MILESTONE_LABELS
            summary, icon = labels.get(name, name.replace("_", " ").capitalize()), "🔋"
            if detail and ("Imin=" in detail or "Vmax=" in detail):
                summary += " - " + detail[:65]
        else:
            summary, icon = name.replace("_", " ").capitalize(), "📋"
            if detail:
                # Keep only short, human-relevant recorded detail; omit key/value diagnostics.
                words = [p.strip() for p in detail.split(" | ") if "=" not in p]
                if words:
                    summary += " · " + "; ".join(words)

        if metrics and name not in {"SESSION_START", "STAGE_CHANGE", "SESSION_STOP", "START", *MAIN_MINIMUM_PREFIXES}:
            summary += f" ({metrics})"
        return f"[{clock}] {icon} <b>{_escape_limited(stage, JOURNAL_STAGE_HTML_MAX)}</b> — {_escape_limited(summary, JOURNAL_SUMMARY_HTML_MAX)}"
    except Exception:
        return f"<code>{_escape_limited(event_line, JOURNAL_RAW_HTML_MAX)}</code>"


def render_journal_text(events: Iterable[str], *, shown: int = JOURNAL_DEFAULT_SHOWN) -> str:
    visible = operator_journal_events(events)
    if not visible:
        return "<b>📝 Логи событий</b>\n\nНет событий для оператора."
    lines = ["<b>📝 Логи событий</b>"]
    for event in visible[-max(0, int(shown)):]:
        lines.append(format_journal_event(event))
    return "\n".join(lines)
