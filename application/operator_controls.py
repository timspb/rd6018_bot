"""Observe-only operator presentation controls."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from .operator_graph import GraphRange


class OperatorControl(str, Enum):
    PAUSE = "operator_pause"
    STOP = "operator_stop"
    REFRESH = "operator_refresh"


@dataclass(frozen=True)
class OperatorPresentationState:
    selected_range: GraphRange = GraphRange.THIRTY_MINUTES

    def select_range(self, selected: GraphRange) -> "OperatorPresentationState":
        return replace(self, selected_range=selected)


@dataclass(frozen=True)
class PresentationButton:
    label: str
    callback: str
    presentation_only: bool = True


def range_buttons() -> tuple[PresentationButton, ...]:
    return (
        PresentationButton("30м", GraphRange.THIRTY_MINUTES.value),
        PresentationButton("2ч", GraphRange.TWO_HOURS.value),
        PresentationButton("Сессия", GraphRange.SESSION.value),
        PresentationButton("Лог", GraphRange.LOG.value),
    )


def action_buttons() -> tuple[PresentationButton, ...]:
    return (
        PresentationButton("Пауза", OperatorControl.PAUSE.value),
        PresentationButton("Стоп", OperatorControl.STOP.value),
        PresentationButton("Обновить", OperatorControl.REFRESH.value),
    )


__all__ = ["OperatorControl", "OperatorPresentationState", "PresentationButton", "action_buttons", "range_buttons"]
