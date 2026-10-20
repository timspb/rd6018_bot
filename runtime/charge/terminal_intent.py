"""Typed caller intent for the canonical terminal session save."""

from __future__ import annotations

from dataclasses import dataclass


DONE_COMPLETION_STORAGE = "storage"
DONE_COMPLETION_TERMINAL = "terminal"
DONE_OUTPUT_ON = "on"
DONE_OUTPUT_OFF = "off"


@dataclass(frozen=True)
class TerminalPersistenceRequest:
    """Terminal outcome and evidence snapshot; contains no persisted document."""

    completion_kind: str
    output_intent: str
    voltage_v: float
    current_a: float
    ah: float

    def __post_init__(self) -> None:
        if (self.completion_kind, self.output_intent) not in (
            (DONE_COMPLETION_STORAGE, DONE_OUTPUT_ON),
            (DONE_COMPLETION_TERMINAL, DONE_OUTPUT_OFF),
        ):
            raise ValueError("unsupported terminal persistence intent")
