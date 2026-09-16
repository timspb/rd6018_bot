"""Canonical read-only observation source for the operator snapshot provider."""

from __future__ import annotations

import inspect
from typing import Any, Mapping

from operator_hmi import (
    HmiAuthority,
    HmiProcessState,
    OperatorHmiState,
    build_operator_hmi_state,
)
from rd6018_telemetry import telemetry_freshness
from runtime.diagnostics import DiagnosticAuthority
from runtime.journal import format_entry


class OperatorObservationSource:
    """Read-only composition boundary for live operator observations.

    This source reads the preserved V2 application and its already-existing
    telemetry/journal surfaces. It does not expose or invoke actuator methods.
    """

    def __init__(self, app: Any, *, journal: Any = None) -> None:
        self._app = app
        self._journal = journal

    async def read_live(self) -> Mapping[str, Any]:
        return await self._app.hass.get_all_live()

    def hmi_state(self, live: Mapping[str, Any]) -> Any:
        return build_operator_hmi_state(self._app, live)

    def get(self, name: str, default: Any = None) -> Any:
        return getattr(self._app, name, default)

    def controller(self) -> Any:
        return self.get("charge_controller")

    def manual_request(self) -> Any:
        manager = self.get("manual_session_manager")
        return getattr(manager, "request", None)

    def observer(self) -> Any:
        return self.get("rd_live_mix_observer")

    def pause_active(self) -> bool:
        checker = self.get("_operator_pause_active")
        return bool(checker()) if callable(checker) else False

    def journal(self) -> Any:
        return self._journal or self.get("journal_recorder") or self.get("journal")

    @staticmethod
    def freshness(live: Mapping[str, Any], fields: tuple[str, ...]) -> bool:
        return telemetry_freshness(live, fields).valid

    @staticmethod
    def format_journal_entry(entry: Any) -> str:
        return format_entry(entry) if hasattr(entry, "short_message") else str(entry)

    @staticmethod
    def hmi_from_snapshot(snapshot: Any) -> OperatorHmiState:
        process = {
            "IDLE": HmiProcessState.IDLE,
            "CHARGING": HmiProcessState.RUNNING,
            "FAULT": HmiProcessState.CONTAINMENT,
        }.get(snapshot.state, HmiProcessState.CONTAINMENT)
        view = snapshot.snapshot
        authority_value = str(view.charge.program or "").lower()
        authority = HmiAuthority.MANUAL if authority_value == HmiAuthority.MANUAL.value else (
            HmiAuthority.AUTO if snapshot.state == "CHARGING" else (
                HmiAuthority.NONE if snapshot.state == "IDLE" else HmiAuthority.CONTAINMENT
            )
        )
        return OperatorHmiState(
            process_state=process,
            authority=authority,
            title=f"RD6018 · {view.charge.stage}",
            output_on=bool(view.output.get("enabled")),
            regulator=view.charge.phase or "—",
            battery_label=str(view.battery.get("label", "") or ""),
            battery_voltage_v=view.telemetry.voltage,
            current_a=view.telemetry.current,
            power_w=view.output.get("power_w"),
            battery_temp_c=view.telemetry.temperature,
            psu_temp_c=view.telemetry.psu_temperature,
            target_voltage_v=view.charge.targets.get("voltage"),
            current_limit_a=view.charge.targets.get("current"),
            progress="" if authority_value == HmiAuthority.MANUAL.value else (view.charge.waiting_for or ""),
            safety=view.safety.reason or ("Защита: норма" if view.safety.allowed else "⚠️ Safety blocked"),
            attention="normal" if view.safety.allowed else "alarm",
            stage_status=str(view.charge.evidence.get("stage_status", "") or ""),
            stage_time=view.charge.timer_text,
            delivered_ah=view.telemetry.accumulated_ah,
        )


__all__ = ["OperatorObservationSource", "DiagnosticAuthority", "HmiProcessState"]
