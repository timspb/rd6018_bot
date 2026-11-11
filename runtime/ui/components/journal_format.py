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


def _event_fields(raw: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in raw.split(" | ")[1:]:
        key, separator, value = part.partition("=")
        if separator and key.strip():
            fields[key.strip()] = value.strip()
    return fields


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
        elif name == "MIX_PROGRESS":
            fields = _event_fields(raw)
            if fields.get("evidence") != "fresh":
                summary = "MIX · нет актуального подтверждённого анализа"
            else:
                mode = fields.get("mode", "unknown")
                if mode == "CC":
                    summary = (
                        f"MIX CC · Vmax {fields.get('Vmax', '—')} · "
                        f"ΔV {fields.get('delta_v', '—')}/"
                        f"{fields.get('required_delta_v', '—')} В"
                    )
                elif mode == "CV":
                    summary = (
                        f"MIX CV · Imin {fields.get('Imin', '—')} · "
                        f"ΔI {fields.get('delta_a', '—')}/"
                        f"{fields.get('required_delta_a', '—')} А"
                    )
                else:
                    summary = "MIX · режим CC/CV не подтверждён"
                if fields.get("confirmations"):
                    summary += f" · подтверждений {fields['confirmations']}"
                if fields.get("hold_elapsed_s"):
                    summary += (
                        f" · выдержка идёт {int(float(fields['hold_elapsed_s']) // 60)}м"
                    )
            icon = "📈"
        elif name == "MIX_STARTED":
            fields = _event_fields(raw)
            reason = fields.get("reason", "").replace("_", " ")
            target = ""
            if "target_voltage_v" in fields and "target_current_a" in fields:
                target = (
                    f" · цель {fields['target_voltage_v'].replace('.', ',')} В"
                    f" / {fields['target_current_a'].replace('.', ',')} А"
                )
            evidence = []
            if fields.get("main_imin_a"):
                evidence.append(f"Imin {fields['main_imin_a']} А")
            if fields.get("main_hold_age_s") and fields.get("main_hold_required_s"):
                age_m = int(float(fields["main_hold_age_s"]) // 60)
                required_m = int(float(fields["main_hold_required_s"]) // 60)
                evidence.append(f"выдержка {age_m}м/{required_m}м")
            if fields.get("main_delta_a") and fields.get("main_required_delta_a"):
                evidence.append(f"ΔI {fields['main_delta_a']}/{fields['main_required_delta_a']} А")
            if fields.get("temperature_c"):
                evidence.append(f"T {fields['temperature_c']}°C")
            summary = "Начат MIX" + (f" · причина: {reason}" if reason else "") + target
            if evidence:
                summary += " · " + "; ".join(evidence)
            icon = "🚀"
        elif name.startswith("END"):
            summary, icon = "Этап завершён", "✅"
            fields = [x.strip() for x in raw.partition("|")[2].split(" | ") if x.strip()]
            useful = [x for x in fields if not x.lower().startswith(("время:", "ёмкость:", "t:", "v:", "i:"))]
            if useful:
                summary += " · " + "; ".join(useful)
        elif name == "TEMP_SOURCE":
            fields = _event_fields(raw)
            summary = (
                f"Источник температуры АКБ: {fields.get('source', 'unknown')} · "
                f"{fields.get('entity_id', 'unknown')} · "
                f"{fields.get('status', 'unknown')} · возраст {fields.get('age_s', 'unknown')}с"
            )
            icon = "🌡"
        elif upper.startswith(("WARNING", "TEMP", "TEMPERATURE")):
            summary, icon = f"Предупреждение: {name.removeprefix('WARNING_').replace('_', ' ').lower()}", "⚠️"
        elif upper.startswith("BANK_FAULT_"):
            summary, icon = f"Обнаружена неисправность банки АКБ ({name.removeprefix('BANK_FAULT_')})", "⚠️"
        elif "STOP" in upper or "TRIP" in upper or "EMERGENCY" in upper or upper in {"OVP_TRIGGERED", "OCP_TRIGGERED"}:
            labels = {"OVP_TRIGGERED": "Сработала защита по перенапряжению", "OCP_TRIGGERED": "Сработала защита по току", "MANUAL_OFF": "Заряд остановлен вручную"}
            summary, icon = labels.get(name, f"Остановка или авария: {name.replace('_', ' ').lower()}"), "🛑"
        elif upper.startswith("V2_FINISH_HOLD_START"):
            fields = _event_fields(raw)
            if "mode" not in fields:
                summary, icon = "Delta подтверждён; началась финишная выдержка", "⏱️"
                if detail:
                    summary += f" · {detail.strip()}"
            else:
                mode = fields.get("mode", "?")
                hold_s = float(fields.get("hold_seconds", "0") or 0)
                hold_label = f"{hold_s / 3600:g}ч" if hold_s >= 3600 else f"{hold_s / 60:g}м"
                if mode == "CV":
                    proof = f"Imin {fields.get('Imin', '—')} · ΔI {fields.get('delta_a', '—')}/{fields.get('required_delta_a', '—')} А"
                elif mode == "CC":
                    proof = f"Vmax {fields.get('Vmax', '—')} · ΔV {fields.get('delta_v', '—')}/{fields.get('required_delta_v', '—')} В"
                else:
                    proof = "режим не подтверждён"
                summary, icon = f"Delta подтверждён ({mode}); выдержка {hold_label} · {proof}", "⏱️"
        elif upper.startswith("V2_COOLING_FAIL_CLOSED"):
            summary, icon = "Аварийно остановлено: ошибка охлаждения", "🛑"
        elif name in MAIN_MINIMUM_PREFIXES:
            fields = _event_fields(raw)
            value_raw = fields.get("Imin", "—").removesuffix("A")
            if "." in value_raw:
                value_raw = value_raw.rstrip("0").rstrip(".")
            value = value_raw.replace(".", ",")
            age = fields.get("age_s")
            delta = fields.get("delta_a")
            required = fields.get("required_delta_a")
            suffix = []
            if age is not None:
                suffix.append(f"возраст минимума {int(float(age))}с")
            if delta is not None and required is not None:
                suffix.append(f"ΔI {delta}/{required} А")
            confirmations = fields.get("confirmations")
            if confirmations is not None:
                suffix.append(f"подтверждений {confirmations}/3")
            summary = f"{MAIN_MINIMUM_PREFIXES[name]} {value} А"
            if suffix:
                summary += " · " + "; ".join(suffix)
            icon = "🔋"
        elif name in {"MIX_IMIN_UPDATED", "MIX_VMAX_UPDATED", "MIX_DELTA_CONFIRMED"}:
            fields = _event_fields(raw)
            mode = fields.get("mode", "?")
            if name == "MIX_IMIN_UPDATED":
                summary = f"Новый Imin MIX {fields.get('Imin', '—')}"
                if fields.get("delta_a") and fields.get("required_delta_a"):
                    summary += f" · ΔI {fields['delta_a']}/{fields['required_delta_a']} А"
            elif name == "MIX_VMAX_UPDATED":
                summary = f"Новый Vmax MIX {fields.get('Vmax', '—')}"
                if fields.get("delta_v") and fields.get("required_delta_v"):
                    summary += f" · ΔV {fields['delta_v']}/{fields['required_delta_v']} В"
            elif mode == "CV":
                summary = f"Delta CV подтверждён · Imin {fields.get('Imin', '—')} · ΔI {fields.get('delta_a', '—')}/{fields.get('required_delta_a', '—')} А"
            else:
                summary = f"Delta CC подтверждён · Vmax {fields.get('Vmax', '—')} · ΔV {fields.get('delta_v', '—')}/{fields.get('required_delta_v', '—')} В"
            if fields.get("age_s"):
                summary += f" · возраст {int(float(fields['age_s']))}с"
            if fields.get("confirmations"):
                summary += f" · {fields['confirmations']}/3 подтверждений"
            icon = "🎯" if name == "MIX_DELTA_CONFIRMED" else "🔋"
        elif upper.startswith(("MAIN_HOLD", "MIX", "DELTA", "I_MIN", "IMIN", "V_MAX", "VMAX", "STABIL")):
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
