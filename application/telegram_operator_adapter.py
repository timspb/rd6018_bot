"""Read-only Telegram presentation adapter for the V3 dashboard snapshot.

This module deliberately has no Telegram client/handler dependency. A caller
may pass the returned text to an existing presentation surface, but this
adapter cannot receive or execute commands.
"""

from __future__ import annotations

from typing import Any

from .operator_dashboard_composer import OperatorDashboardState
from .charge_card import ChargeCardFormatter, ChargeCardViewModel
from .operator_panel import OperatorPanelViewModel, TelegramOperatorPanelFormatter


class TelegramOperatorViewAdapter:
    """Format one immutable dashboard state into operator-facing text."""

    def format(self, state: OperatorDashboardState) -> str:
        if not isinstance(state, OperatorDashboardState):
            raise TypeError("OperatorDashboardState is required")
        lines = [
            "👁 V3 · НАБЛЮДЕНИЕ",
            f"🔋 {self._value(state.current_session.profile)} · {self._value(state.current_session.state)} · {self._value(state.current_session.phase)}",
            f"⚡ {self._number(state.telemetry.voltage, 'V')} · {self._number(state.telemetry.current, 'A')} · {self._number(state.telemetry.power, 'W')}",
            f"🌡 {self._number(state.telemetry.temperature, '°C')} · источник: {state.telemetry.source} · confidence: {state.telemetry.confidence}",
            f"🧭 identity: {state.current_session.identity_status}",
            "",
            "📈 TIMELINE",
        ]
        if state.timeline.session_id == "UNKNOWN":
            lines.append("UNKNOWN · текущая timeline недоступна")
        else:
            lines.append(f"session {state.timeline.session_id} · событий: {state.timeline.event_count}")
            if state.timeline.event_count == 0:
                lines.append("события не зафиксированы")
        if state.explanation is not None:
            decision = state.explanation.decision
            phase = state.explanation.phase
            lines.extend(("", "🧠 EXPLANATION", f"стратегия: {self._value(decision.strategy)}", f"почему: {self._value(decision.reason)}", f"next: {self._value(decision.expected_next_transition)}", f"условия: {self._list(phase.transition_conditions)}", f"не выполнено: {self._list(phase.unmet_conditions)}"))
        lines.extend(("", "🛡 SAFETY", f"protection: {self._mapping(state.safety.protection)}", f"lease: {self._mapping(state.safety.lease)}", f"stale: {self._list(state.safety.stale)}", f"warnings: {self._list(state.diagnostics.warnings)}", f"blockers: {self._list(state.diagnostics.blockers)}", f"historical: {self._list(state.explanation.safety.historical_faults if state.explanation is not None else ())}", "", f"🔎 parity: {state.parity.status}", f"🧪 canary: {state.canary.status} · {self._list(state.canary.blockers)}", "⛔ CONTROL: недоступен"))
        return "\n".join(lines)

    def format_charge_card(self, model: ChargeCardViewModel) -> str:
        """Render the compact charge card; diagnostics remain a separate view."""
        return ChargeCardFormatter().format(model)

    def format_operator_panel(self, panel: OperatorPanelViewModel) -> str:
        """Format graphs + compact card + presentation controls + current log."""
        return TelegramOperatorPanelFormatter().format(panel)

    @staticmethod
    def _value(value: Any) -> str:
        return "UNKNOWN" if value in (None, "") else str(value)

    @staticmethod
    def _number(value: Any, unit: str) -> str:
        return "UNKNOWN" if value is None else f"{float(value):.2f} {unit}"

    @staticmethod
    def _list(values: Any) -> str:
        values = tuple(values or ())
        return ", ".join(str(value) for value in values) if values else "нет"

    @staticmethod
    def _mapping(value: Any) -> str:
        if not value:
            return "UNKNOWN"
        return ", ".join(f"{key}={item}" for key, item in value.items())


__all__ = ["TelegramOperatorViewAdapter"]
