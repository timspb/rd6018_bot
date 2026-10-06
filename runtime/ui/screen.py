"""Framework-neutral screen contracts and charge-screen completeness checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .buttons import ButtonSpec
from .models import ChargeView


class ScreenId(str, Enum):
    HOME = "home"
    CHARGE = "charge"
    BATTERIES = "batteries"
    MANUAL = "manual"
    DIAGNOSTICS = "diagnostics"
    RECOVERY = "recovery"
    MIX = "mix"
    SETTINGS = "settings"
    SERVICE = "service"
    GRAPH = "graph"
    JOURNAL = "journal"
    ENTITIES = "entities"
    HELP = "help"
    STATS = "stats"
    ANALYSIS = "analysis"
    OFF_CONDITIONS = "off_conditions"


@dataclass(frozen=True)
class ScreenSpec:
    """Declarative screen payload; transport rendering lives elsewhere."""

    screen_id: ScreenId
    title: str
    body: str
    buttons: tuple[tuple[ButtonSpec, ...], ...] = ()

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("screen title is required")


REQUIRED_SCREEN_FIELDS = (
    "stage",
    "program",
    "targets",
    "active_limits",
    "waiting_for",
    "conditions",
)


def missing_charge_screen_fields(view: ChargeView) -> tuple[str, ...]:
    missing = []
    for field in REQUIRED_SCREEN_FIELDS:
        value = getattr(view, field)
        if field in {"stage", "program"} and not str(value).strip():
            missing.append(field)
        elif field in {"targets", "active_limits", "conditions"} and not value:
            missing.append(field)
        elif field == "waiting_for" and not value:
            missing.append(field)
    return tuple(missing)


__all__ = [
    "REQUIRED_SCREEN_FIELDS",
    "ScreenId",
    "ScreenSpec",
    "missing_charge_screen_fields",
]
