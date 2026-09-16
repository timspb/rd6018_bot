"""Read-only DTOs used by operator detail screens."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OperatorDetailsView:
    process_state: str
    authority: str
    output_on: bool
    regulator: str
    battery_label: str
    battery_voltage_v: float | None
    current_a: float | None
    battery_temp_c: float | None
    psu_temp_c: float | None
    target_voltage_v: float | None
    current_limit_a: float | None
    safety: str
    progress: str = ""
    observer_state: str = ""
    observer_status: str = ""
    stage: str = ""
    battery_type: str = ""
    capacity_ah: float | None = None
    stage_time: str = "—"
    total_time: str = "—"
    remaining_time: str = "—"
    delivered_ah: float | None = None
    input_voltage_v: float | None = None
    uptime: str = "—"
    manual_capacity_ah: float | None = None


@dataclass(frozen=True)
class ServiceDetailsView:
    authority: str
    output_on: bool
    regulator: str
    stage: str = "—"
    v2_analysis: str = "unavailable"
    decision: str = "—"
    ovp_v: float | None = None
    ocp_a: float | None = None
    protection: str = "—"
    regulation: str = "—"
    heartbeat: str = "—"
