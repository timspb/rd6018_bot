"""Pure journal presentation helpers.

No Telegram, runtime/controller, HA, ESPHome or actuator imports are allowed
here. The functions preserve the accepted V2 event-log presentation while the
screen owner moves to the modular UI.
"""

from __future__ import annotations

from datetime import datetime
import html
import re
from typing import Iterable


def collapse_noisy_events(events: Iterable[str]) -> list[str]:
    events = list(events)
    if not events:
        return events
    collapsed: list[str] = []
    run_event: str | None = None
    run_count = 0

    def flush() -> None:
        nonlocal run_event, run_count
        if not run_event:
            return
        if run_count <= 1:
            collapsed.append(run_event)
        else:
            parts = run_event.split(" | ")
            if len(parts) > 6:
                parts[6] = f"{parts[6].strip()} (x{run_count})"
                collapsed.append(" | ".join(parts))
            else:
                collapsed.append(run_event)
        run_event = None
        run_count = 0

    for event in events:
        parts = event.split(" | ")
        event_name = parts[6].strip() if len(parts) > 6 else ""
        if event_name == "EMERGENCY_UNAVAILABLE":
            if run_event is None:
                run_event = event
                run_count = 1
            else:
                run_count += 1
            continue
        flush()
        collapsed.append(event)
    flush()
    return collapsed


def normalize_journal_events(events: Iterable[str]) -> list[str]:
    """Compress noisy duplicates while preserving transition/state ordering."""

    source = collapse_noisy_events(events)
    if not source:
        return source

    filtered: list[str] = []
    restore_count = 0
    last_restore_event: str | None = None
    last_restore_stage: str | None = None
    emergency_count = 0
    last_emergency_event: str | None = None
    last_emergency_stage: str | None = None
    last_emergency_ts: datetime | None = None

    def parse_ts(event: str) -> datetime | None:
        try:
            raw = event.split(" | ", 1)[0].strip("[]")
            return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None

    def flush_restore() -> None:
        nonlocal restore_count, last_restore_event, last_restore_stage
        if not last_restore_event:
            return
        if restore_count > 1:
            parts = last_restore_event.split(" | ")
            if len(parts) > 6:
                parts[6] = f"RESTORE (x{restore_count})"
                filtered.append(" | ".join(parts))
            else:
                filtered.append(last_restore_event)
        else:
            filtered.append(last_restore_event)
        restore_count = 0
        last_restore_event = None
        last_restore_stage = None

    def flush_emergency() -> None:
        nonlocal emergency_count, last_emergency_event, last_emergency_stage, last_emergency_ts
        if not last_emergency_event:
            return
        if emergency_count > 1:
            parts = last_emergency_event.split(" | ")
            if len(parts) > 6:
                parts[6] = f"EMERGENCY_UNAVAILABLE (x{emergency_count})"
                filtered.append(" | ".join(parts))
            else:
                filtered.append(last_emergency_event)
        else:
            filtered.append(last_emergency_event)
        emergency_count = 0
        last_emergency_event = None
        last_emergency_stage = None
        last_emergency_ts = None

    for event in source:
        parts = event.split(" | ")
        if len(parts) > 6:
            event_field = parts[6].strip()
            event_type = event_field.split()[0] if event_field else ""
            stage = parts[1].strip()
            if event_type == "RESTORE":
                flush_emergency()
                if last_restore_event and last_restore_stage == stage:
                    restore_count += 1
                    last_restore_event = event
                else:
                    flush_restore()
                    restore_count = 1
                    last_restore_event = event
                    last_restore_stage = stage
                continue
            if event_type == "EMERGENCY_UNAVAILABLE":
                current_ts = parse_ts(event)
                if (
                    last_emergency_event
                    and last_emergency_stage == stage
                    and last_emergency_ts
                    and current_ts
                    and (current_ts - last_emergency_ts).total_seconds() <= 600
                ):
                    emergency_count += 1
                    last_emergency_event = event
                    last_emergency_ts = current_ts
                    continue
                flush_restore()
                flush_emergency()
                emergency_count = 1
                last_emergency_event = event
                last_emergency_stage = stage
                last_emergency_ts = current_ts
                continue
        flush_emergency()
        flush_restore()
        filtered.append(event)

    flush_emergency()
    flush_restore()
    return filtered


def format_journal_event(event_line: str) -> str:
    """Format one accepted charge event using the established operator notation."""

    try:
        parts = event_line.split(" | ")
        if len(parts) < 6:
            return f"<code>{html.escape(event_line)}</code>"

        timestamp = parts[0].strip("[]")
        stage = parts[1].strip()
        event = " | ".join(parts[6:]).strip() if len(parts) > 6 else ""
        time_only = timestamp.split(" ")[1][:5] if " " in timestamp else timestamp[-8:-3]
        stage_short = (
            stage.replace("Main Charge", "Main")
            .replace("Десульфатация", "Desulf")
            .replace("Безопасное ожидание", "Wait")
        )
        stage_escaped = html.escape(stage_short)

        if event.startswith("SESSION_"):
            event_tail = event.replace("SESSION_", "", 1).strip()
            text = f"[{time_only}] 📘 <b>{stage_escaped}: {html.escape(event_tail.split(' | ')[0])}</b>\n"
            for part in event.split(" | ")[1:]:
                part = part.strip()
                if not part or "=" not in part:
                    continue
                key, value = part.split("=", 1)
                key = key.strip()
                value = value.strip()
                if key == "rules":
                    text += f"└ Правила: {html.escape(value)}\n"
                elif key == "profile":
                    text += f"└ Профиль: {html.escape(value)}\n"
                elif key == "capacity_ah":
                    text += f"└ Емкость: {html.escape(value)}Ah\n"
                elif key != "kind":
                    text += f"└ {html.escape(key)}: {html.escape(value)}\n"
            return text.rstrip()

        if event.startswith("EMERGENCY_UNAVAILABLE"):
            return f"[{time_only}] 🧯 <b>{stage_escaped}</b>: {html.escape(event)}"

        if event.startswith("BANK_FAULT_"):
            summary = event.replace("BANK_FAULT_", "КЗ банки: ", 1)
            return f"[{time_only}] ⚠️ <b>{stage_escaped}</b>: {html.escape(summary)}"

        if event.startswith("END |"):
            text = f"[{time_only}] 📉 <b>{stage_escaped}: завершён</b>\n"
            for part in event[5:].strip().split(" | "):
                part = part.strip()
                if ":" in part:
                    key, value = part.split(":", 1)
                    text += f"└ {key.strip()}: {value.strip()}\n"
            return text.rstrip()

        if event.strip().startswith("└"):
            return f"[{time_only}] └ {html.escape(event.strip()[1:].strip())}"

        if event.startswith("START"):
            text = f"[{time_only}] 🏁 <b>{stage_escaped}: START</b>\n"
            if "Емкость:" in event:
                match = re.search(r"Емкость:\s*(\d+)\s*Ah", event, re.IGNORECASE)
                if match:
                    text += f"└ Емкость: {match.group(1)}Ah\n"
            if "profile=" in event:
                for profile in ("EFB", "AGM", "Ca/Ca"):
                    if profile in event:
                        text += f"└ Профиль: {profile}\n"
                        break
            if "CUSTOM" in event and "profile=" not in event:
                text += "└ Профиль: Custom\n"
            return text.rstrip()

        if event.startswith("STAGE_CHANGE |"):
            transition = event.replace("STAGE_CHANGE |", "", 1).strip()
            return f"[{time_only}] >> <b>{stage_escaped}</b>: {html.escape(transition)}"

        if "CHECKPOINT" in event or "RESTORE" in event:
            return ""
        icon = "📋"
        if "DONE" in event or "FINISH" in event:
            icon = "✅"
        elif "STOP" in event or "EMERGENCY" in event:
            icon = "🛑"
        elif "WARNING" in event or "TEMP" in event:
            icon = "⚠️"
        return f"[{time_only}] {icon} <b>{stage_escaped}</b>: {html.escape(event)}"
    except Exception:
        return f"<code>{html.escape(event_line[:100])}</code>"


def render_journal_text(events: Iterable[str], *, shown: int = 25) -> str:
    """Render the complete journal screen with legacy-compatible semantics."""

    normalized = normalize_journal_events(events)
    if not normalized:
        return "<b>📝 Логи событий</b>\n\nНет событий."
    lines = ["<b>📝 Логи событий</b>\n"]
    for event in normalized[-max(0, int(shown)):]:
        formatted = format_journal_event(event)
        if formatted.strip():
            lines.append(formatted)
    if len(lines) <= 1:
        return "<b>📝 Логи событий</b>\n\nТолько служебные события."
    return "\n".join(lines)
