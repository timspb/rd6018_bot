"""Read-only operator panel composition: graphs, card, controls and log."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .charge_card import ChargeCardFormatter, ChargeCardViewModel
from .operator_controls import PresentationButton, action_buttons, range_buttons
from .operator_graph import GraphSample, GraphViewModel
from .operator_log import OperatorLogViewModel
from .operator_state import OperatorStateSnapshot
from v3_core.canonical_events import CanonicalChargeEvent


@dataclass(frozen=True)
class ControlsState:
    range_buttons: tuple[PresentationButton, ...]
    action_buttons: tuple[PresentationButton, ...]
    selected_range: Any
    presentation_only: bool = True


@dataclass(frozen=True)
class OperatorPanelState:
    graphs: GraphViewModel
    card: ChargeCardViewModel
    controls: ControlsState
    log: OperatorLogViewModel
    diagnostics_reference: Any = None
    observe_only: bool = True

    @property
    def range_buttons(self) -> tuple[PresentationButton, ...]:
        return self.controls.range_buttons

    @property
    def action_buttons(self) -> tuple[PresentationButton, ...]:
        return self.controls.action_buttons

    @classmethod
    def compose(
        cls,
        snapshot: OperatorStateSnapshot,
        *,
        samples: tuple[GraphSample, ...] = (),
        events: tuple[CanonicalChargeEvent, ...] = (),
        selected_range=None,
        now: float | None = None,
        diagnostics_reference: Any = None,
        **card_metrics,
    ) -> "OperatorPanelState":
        from .operator_graph import GraphRange
        selected_range = selected_range or GraphRange.THIRTY_MINUTES
        session_id = snapshot.session_id or "UNKNOWN"
        return cls(
            GraphViewModel.from_samples(samples, session_id=session_id, selected_range=selected_range, now=now),
            ChargeCardViewModel.from_snapshot(snapshot, **card_metrics),
            ControlsState(range_buttons(), action_buttons(), selected_range),
            OperatorLogViewModel.from_events(events, session_id=session_id, trace_id=snapshot.trace_id),
            diagnostics_reference,
            True,
        )


class TelegramOperatorPanelFormatter:
    """Format only the operator panel; diagnostics are intentionally absent."""

    def format(self, panel: "OperatorPanelState") -> str:
        graph_lines = tuple(
            f"📈 {series.name}: {len(series.points)} points"
            for series in (panel.graphs.voltage, panel.graphs.current, panel.graphs.battery_temperature)
        )
        ranges = " · ".join(button.label for button in panel.range_buttons)
        actions = " · ".join(button.label for button in panel.action_buttons)
        return "\n".join((*graph_lines, ChargeCardFormatter().format(panel.card), f"{ranges}", f"{actions}"))


# Compatibility name for callers introduced during the earlier panel pass.
OperatorPanelViewModel = OperatorPanelState

__all__ = ["ControlsState", "OperatorPanelState", "OperatorPanelViewModel", "TelegramOperatorPanelFormatter"]
