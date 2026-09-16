"""Audit records for opt-in physical bridge attempts."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Any


@dataclass(frozen=True)
class PhysicalExecutionRecord:
    timestamp: float
    command_plan: Any
    operator: str
    gate_state: str
    actions: tuple[str, ...] = ()
    readback: Any = None
    result: str = ""
    error: str | None = None


class PhysicalExecutionAudit:
    def __init__(self) -> None:
        self.records: list[PhysicalExecutionRecord] = []

    def record(self, plan: Any, operator: str, gate_state: str, *, actions=(), readback=None, result="", error=None):
        record = PhysicalExecutionRecord(time(), plan, operator, gate_state, tuple(actions), readback, result, error)
        self.records.append(record)
        return record

