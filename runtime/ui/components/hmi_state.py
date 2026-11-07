"""Immutable operator HMI read model; no runtime/control ownership."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional

class HmiProcessState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STORAGE = "storage"
    CONTAINMENT = "containment"
    HANDS_OFF = "hands_off"
    ADOPTED_MIX = "adopted_mix"
    INTERRUPTED = "interrupted"


class HmiAuthority(str, Enum):
    NONE = "none"
    AUTO = "auto"
    MANUAL = "manual"
    EXTERNAL = "external"
    ADOPTED_MIX = "adopted_mix"
    CONTAINMENT = "containment"


@dataclass(frozen=True)
class OperatorHmiState:
    process_state: HmiProcessState
    authority: HmiAuthority
    title: str
    output_on: bool
    regulator: str
    battery_label: str
    battery_voltage_v: Optional[float]
    current_a: Optional[float]
    power_w: Optional[float]
    battery_temp_c: Optional[float]
    psu_temp_c: Optional[float]
    target_voltage_v: Optional[float]
    current_limit_a: Optional[float]
    progress: str
    safety: str
    attention: str = "normal"
    stage_status: str = ""
    finish_evidence: Optional[Mapping[str, Any]] = None
    stage_time: str = ""
    total_time: str = ""
    delivered_ah: Optional[float] = None
    manual_interrupted: bool = False
