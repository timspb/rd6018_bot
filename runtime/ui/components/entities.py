"""Framework-neutral entity-status formatter."""

from __future__ import annotations

import html

from runtime.ui.models import EntityStatusView


def render_entities_body(view: EntityStatusView) -> str:
    if view.error:
        return f"❌ Ошибка опроса: {html.escape(view.error)}"

    items = tuple(view.items)
    ok_count = sum(1 for item in items if item.status == "ok")
    lines = [f"✅ Доступно: {ok_count}/{len(items)}", ""]
    for item in items:
        key = html.escape(item.key)
        state_raw = item.state
        if item.status == "ok" and state_raw is not None:
            try:
                state = html.escape(f"{float(state_raw):.3f}")
            except (TypeError, ValueError):
                state = html.escape(str(state_raw))
        else:
            state = html.escape(str(state_raw) if state_raw is not None else "")
        unit = html.escape(item.unit or "")
        if item.status == "ok":
            lines.append(f"🟢 <b>{key}</b>: {state} {unit}".strip())
        else:
            icon = "🔴" if item.status == "error" else "🟡"
            lines.append(f"{icon} <b>{key}</b>: {html.escape(item.status)} ({state})")

    text = "\n".join(lines)
    if len(text) > 3950:
        text = "\n".join(lines[:2] + [f"… всего {len(items)} сущностей"] + lines[2:24])
    return text


__all__ = ["render_entities_body"]
