"""Declarative panel actions; no callbacks or runtime objects."""

from __future__ import annotations

from dataclasses import dataclass

from application.intents import OperatorIntentKind


@dataclass(frozen=True)
class PanelAction:
    label: str
    intent: OperatorIntentKind
    parameters: tuple[tuple[str, str], ...] = ()


def actions_for(state: str, safety_allowed: bool) -> tuple[PanelAction, ...]:
    if state == "CHARGING":
        return (PanelAction("STOP", OperatorIntentKind.STOP_CHARGE), PanelAction("LOG", OperatorIntentKind.SHOW_JOURNAL), PanelAction("GRAPH", OperatorIntentKind.SHOW_GRAPH))
    if state == "FAULT":
        return (PanelAction("DIAG", OperatorIntentKind.SHOW_DIAGNOSTICS), PanelAction("ACK", OperatorIntentKind.ACKNOWLEDGE))
    if state == "IDLE" and safety_allowed:
        return (PanelAction("START", OperatorIntentKind.START_CHARGE), PanelAction("LOG", OperatorIntentKind.SHOW_JOURNAL), PanelAction("DIAG", OperatorIntentKind.SHOW_DIAGNOSTICS))
    return (PanelAction("DIAG", OperatorIntentKind.SHOW_DIAGNOSTICS),)
