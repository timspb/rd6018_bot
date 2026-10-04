"""Framework-neutral V3 operator action identifiers."""

from __future__ import annotations

from enum import Enum


class UIAction(str, Enum):
    START_CHARGE = "charge.start"
    STOP_CHARGE = "charge.stop"
    PAUSE_CHARGE = "charge.pause"
    RESUME_CHARGE = "charge.resume"
    SELECT_PROFILE = "charge.select_profile"

    OPEN_HOME = "nav.home"
    OPEN_CHARGE = "nav.charge"
    OPEN_BATTERIES = "nav.batteries"
    OPEN_MANUAL = "nav.manual"
    OPEN_DIAGNOSTICS = "nav.diagnostics"
    OPEN_RECOVERY = "nav.recovery"
    OPEN_MIX = "nav.mix"
    OPEN_SETTINGS = "nav.settings"
    OPEN_SERVICE = "nav.service"
    OPEN_GRAPH = "nav.graph"
    OPEN_JOURNAL = "nav.journal"


__all__ = ["UIAction"]
