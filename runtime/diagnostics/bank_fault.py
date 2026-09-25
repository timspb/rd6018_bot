"""Configurable bank-fault evidence and scoring boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class BankFaultLevel(str, Enum):
    STABLE = "stable"
    WATCH = "watch"
    PROBABLE = "probable"
    HIGH = "high"


@dataclass(frozen=True)
class BankFaultSignal:
    name: str
    value: Any
    timestamp: float
    source: str
    confidence: float = 1.0
    quality: str = "valid"

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.source.strip():
            raise ValueError("bank-fault signal name and source are required")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("bank-fault signal confidence must be between 0 and 1")
        if not self.quality.strip():
            raise ValueError("bank-fault signal quality is required")


@dataclass(frozen=True)
class BankFaultEvidence:
    signals: tuple[BankFaultSignal, ...] = ()

    def signal(self, name: str) -> BankFaultSignal | None:
        return next((item for item in self.signals if item.name == name), None)


@dataclass(frozen=True)
class BankFaultPolicy:
    """Data-only thresholds and weights; algorithm does not own constants."""

    weights: Mapping[str, float] = field(default_factory=lambda: {
        "slow_voltage_rise": 10.0,
        "prolonged_main_duration": 15.0,
        "weak_ah_progress": 10.0,
        "relaxation_decay": 20.0,
        "thermal_without_voltage_gain": 15.0,
        "self_discharge_indicator": 20.0,
        "low_voltage_persistent": 30.0,
    })
    watch_score: float = 15.0
    probable_score: float = 35.0
    high_score: float = 80.0

    def __post_init__(self) -> None:
        if any(not str(key).strip() or float(value) < 0 for key, value in self.weights.items()):
            raise ValueError("bank-fault weights must be non-negative and named")
        if not 0 <= self.watch_score <= self.probable_score <= self.high_score:
            raise ValueError("bank-fault thresholds must be ordered")


def score_bank_fault(evidence: BankFaultEvidence, policy: BankFaultPolicy) -> tuple[float, BankFaultLevel]:
    score = sum(
        float(policy.weights.get(signal.name, 0.0)) * float(signal.confidence)
        for signal in evidence.signals
        if bool(signal.value) and signal.quality == "valid"
    )
    if score >= policy.high_score:
        level = BankFaultLevel.HIGH
    elif score >= policy.probable_score:
        level = BankFaultLevel.PROBABLE
    elif score >= policy.watch_score:
        level = BankFaultLevel.WATCH
    else:
        level = BankFaultLevel.STABLE
    return score, level


class LegacyBankFaultAdapter:
    """Map an existing risk snapshot; never invokes charge/controller code."""

    _FEATURES = (
        "slow_voltage_rise", "prolonged_main_duration", "weak_ah_progress",
        "relaxation_decay", "thermal_without_voltage_gain",
        "self_discharge_indicator", "low_voltage_persistent",
    )

    @classmethod
    def from_snapshot(cls, snapshot: Mapping[str, Any], *, timestamp: float, source: str = "legacy") -> BankFaultEvidence:
        reasons = " ".join(str(item).lower() for item in snapshot.get("reasons", ()) or ())
        aliases = {
            "slow_voltage_rise": ("slow_v_rise", "slow_to_12v", "weak_voltage"),
            "prolonged_main_duration": ("main_duration",),
            "weak_ah_progress": ("low_ah_acceptance",),
            "relaxation_decay": ("decay_", "relaxation"),
            "thermal_without_voltage_gain": ("temp_rise", "thermal"),
            "self_discharge_indicator": ("self_discharge",),
            "low_voltage_persistent": ("start_low", "below_12v"),
        }
        signals = tuple(
            BankFaultSignal(feature, any(alias in reasons for alias in aliases[feature]), timestamp, source)
            for feature in cls._FEATURES
        )
        return BankFaultEvidence(signals)
