"""Human readable formatting for persisted charge journal rows."""

from __future__ import annotations

import html
import re
from typing import Iterable


_SERVICE_PREFIXES = (
    "CHECKPOINT", "RESTORE", "SESSION_RESTORE", "V2_START", "SESSION_PAUSE",
    "OPERATOR_PAUSE_RETIRED",
)
_SERVICE_EXACT: set[str] = set()


def _parts(line: str) -> tuple[str, str, str, str, str, str, str]:
    fields = line.split(" | ", 6)
    fields += [""] * (7 - len(fields))
    return tuple(fields[:7])  # type: ignore[return-value]


def is_operator_journal_event(line: str) -> bool:
    """Drop periodic and service-only rows before page slicing/counting."""
    if len(line.split(" | ", 6)) < 7:
        return bool(line.strip())
    event = _parts(line)[6].strip()
    name = event.split(" | ", 1)[0].strip()
    return not (
        name in _SERVICE_EXACT
        or event.startswith("START | V2_")
        or any(name.startswith(p) for p in _SERVICE_PREFIXES)
    )


def operator_journal_events(events: Iterable[str]) -> list[str]:
    """Return recorded operator events in source (chronological) order."""
    return [str(event) for event in events if is_operator_journal_event(str(event))]


def collapse_noisy_events(events: Iterable[str]) -> list[str]:
    """Compatibility helper retained for existing component exports."""
    return list(events)


def normalize_journal_events(events: Iterable[str]) -> list[str]:
    """Normalize to the actual operator-visible persisted events."""
    return operator_journal_events(events)


def _stage_name(stage: str) -> str:
    stage = stage.strip()
    names = {
        "MAIN": "Основной заряд", "Main Charge": "Основной заряд",
        "MIX": "Финишный заряд", "Mix": "Финишный заряд",
        "DESULFATION": "Восстановление", "Десульфатация": "Восстановление",
        "SAFE_WAIT": "Безопасное ожидание", "Безопасное ожидание": "Безопасное ожидание",
        "PREP": "Подготовка", "COOLING": "Охлаждение", "DONE": "Завершение",
        "Idle": "Ожидание",
    }
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
            return f"<code>{_escape_limited(event_line, 250)}</code>"
        ts, stage_raw, v, i, temp, _ah, event = _parts(event_line)
        timestamp = ts.strip().strip("[]")
        clock = timestamp.split(" ")[-1][:5] if timestamp else "—"
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
        elif upper.startswith(("MAIN_HOLD", "MIX", "DELTA", "I_MIN", "IMIN", "V_MAX", "VMAX", "STABIL")):
            # Only report facts that were actually written to charging_history.log.
            labels = {
                "MAIN_HOLD_START": 'Imin принят; отсчёт от минимума',
                "MAIN_HOLD_RESET": 'Новый Imin; отсчёт от минимума заново',
                "MIX_IMIN_UPDATED": 'Новый минимум тока MIX',
                "MIX_VMAX_UPDATED": 'Новый максимум напряжения MIX',
                "MIX_STARTED": "Начат финишный заряд", "DELTA_CONFIRMED": "Подтверждён Delta",
                "DELTA_HOLD_START": "Началась выдержка после Delta",
                "DELTA_HOLD_RESTART": "Выдержка после Delta началась заново",
                "I_MIN_ACHIEVED": "Достигнут минимальный ток Imin",
                "IMIN_ACHIEVED": "Достигнут минимальный ток Imin",
            }
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

        if metrics and name not in {"SESSION_START", "STAGE_CHANGE", "SESSION_STOP", "START"}:
            summary += f" ({metrics})"
        return f"[{clock}] {icon} <b>{_escape_limited(stage, 60)}</b> — {_escape_limited(summary, 180)}"
    except Exception:
        return f"<code>{_escape_limited(event_line, 250)}</code>"


def render_journal_text(events: Iterable[str], *, shown: int = 25) -> str:
    visible = operator_journal_events(events)
    if not visible:
        return "<b>📝 Логи событий</b>\n\nНет событий для оператора."
    lines = ["<b>📝 Логи событий</b>"]
    for event in visible[-max(0, int(shown)):]:
        lines.append(format_journal_event(event))
    return "\n".join(lines)
