"""Stable view models; no UI framework or runtime ownership imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class TransitionView:
    waiting_for: str
    observed_value: str | None = None
    observed_at: float | None = None
    confirmed: bool = False


@dataclass(frozen=True)
class ChargeView:
    stage: str
    program: str
    started_at: float | None = None
    conditions: tuple[TransitionView, ...] = ()
    timer_text: str = ""
    remaining_hold_seconds: float | None = None
    targets: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class TelemetryView:
    voltage: float | None = None
    current: float | None = None
    temperature: float | None = None
    accumulated_ah: float | None = None


@dataclass(frozen=True)
class DiagnosticsView:
    authority: str = "allow"
    hypotheses: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class SafetyView:
    allowed: bool = True
    reason: str = ""
    violations: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeUISnapshot:
    charge: ChargeView
    battery: Mapping[str, object] = field(default_factory=dict)
    telemetry: TelemetryView = field(default_factory=TelemetryView)
    diagnostics: DiagnosticsView = field(default_factory=DiagnosticsView)
    safety: SafetyView = field(default_factory=SafetyView)
    output: Mapping[str, object] = field(default_factory=dict)
    journal_tail: tuple[str, ...] = ()
