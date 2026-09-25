"""Declarative rows for the operator panel."""

from __future__ import annotations

from dataclasses import dataclass

from application.operator_snapshot import OperatorSnapshot
from .panel_actions import PanelAction, actions_for


@dataclass(frozen=True)
class PanelLayout:
    state: str
    rows: tuple[str, ...]
    actions: tuple[PanelAction, ...]


def layout_for(snapshot: OperatorSnapshot) -> PanelLayout:
    s = snapshot.snapshot
    state = snapshot.state.upper()
    rows: list[str]
    if state == "CHARGING":
        t = s.telemetry
        power = None if t.voltage is None or t.current is None else t.voltage * t.current
        rows = [f"🔋 {s.battery.get('label', 'АКБ')} · CHARGE", f"{s.charge.stage} · {t.voltage or '—'}V {t.current or '—'}A {power or '—'}W", f"⏱{s.charge.timer_text or '—'}", f"🛡{'OK' if s.safety.allowed else 'CHECK'}"]
    elif state == "FAULT":
        reason = s.safety.reason or (snapshot.faults[0] if snapshot.faults else "неизвестная ошибка")
        rows = ["⚠ RD6018 · FAULT", reason, "Output OFF" if s.output.get("enabled") is False else "Output: проверить", "🛡CHECK"]
    else:
        rows = [f"🔋 {s.battery.get('label', 'АКБ')} · READY", f"{s.telemetry.voltage or '—'}V · 🛡{'OK' if s.safety.allowed else 'CHECK'}"]
    return PanelLayout(state, tuple(row for row in rows if row), actions_for(state, s.safety.allowed and snapshot.telemetry_fresh))
