"""Data-only models for manual bench validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Any


@dataclass(frozen=True)
class BenchStep:
    name: str
    command: str | None = None
    readback_required: bool = False


@dataclass(frozen=True)
class BenchScenario:
    scenario_id: str
    operator: str
    timestamp: float
    required_capabilities: tuple[str, ...]
    expected_steps: tuple[BenchStep, ...]
    safety_requirements: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.scenario_id.strip() or not self.operator.strip() or not self.expected_steps:
            raise ValueError("scenario, operator and steps are required")


@dataclass(frozen=True)
class BenchEvidenceRecord:
    timestamp: float
    scenario: str
    operator: str
    command: str
    expected_result: str
    observed_result: str
    readback: Any = None
    passed: bool = False
    notes: str = ""


@dataclass(frozen=True)
class BenchRunResult:
    scenario: BenchScenario
    evidence: tuple[BenchEvidenceRecord, ...]
    passed: bool
    simulated: bool = True

