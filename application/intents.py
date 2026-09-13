"""Operator intents. They are requests, never physical commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class OperatorIntentKind(str, Enum):
    START_CHARGE = "start_charge"
    STOP_CHARGE = "stop_charge"
    SHOW_GRAPH = "show_graph"
    SHOW_JOURNAL = "show_journal"
    SHOW_DIAGNOSTICS = "show_diagnostics"
    REFRESH = "refresh"
    ACKNOWLEDGE = "acknowledge"


@dataclass(frozen=True)
class OperatorIntent:
    kind: OperatorIntentKind
    source: str
    user: str
    parameters: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source.strip() or not self.user.strip():
            raise ValueError("source and user are required")
