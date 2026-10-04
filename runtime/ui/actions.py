"""Framework-neutral V3 operator action identifiers."""

from __future__ import annotations

from enum import Enum


class UIAction(str, Enum):
    START_CHARGE = "charge.start"
    STOP_CHARGE = "charge.stop"
    PAUSE_CHARGE = "charge.pause"
    RESUME_CHARGE = "charge.resume"
    SELECT_PROFILE = "charge.select_profile"
    SET_OFF_PRESET = "charge.set_off_preset"

    OPEN_HOME = "nav.home"
    OPEN_CHARGE = "nav.charge"
    OPEN_BATTERIES = "nav.batteries"
    OPEN_BATTERY_ADD = "nav.battery_add"
    OPEN_MANUAL = "nav.manual"
    OPEN_INTERRUPTED_MANUAL = "nav.manual_interrupted"
    OPEN_DIAGNOSTICS = "nav.diagnostics"
    OPEN_RECOVERY = "nav.recovery"
    OPEN_MIX = "nav.mix"
    OPEN_SETTINGS = "nav.settings"
    OPEN_SERVICE = "nav.service"
    OPEN_GRAPH = "nav.graph"
    OPEN_JOURNAL = "nav.journal"
    OPEN_ENTITIES = "nav.entities"
    OPEN_HELP = "nav.help"
    OPEN_STATS = "nav.stats"
    OPEN_ANALYSIS = "nav.analysis"
    OPEN_OFF_CONDITIONS = "nav.off_conditions"


__all__ = ["UIAction"]
