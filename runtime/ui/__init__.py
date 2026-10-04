"""Transport-independent V3 presentation contracts."""

from .actions import UIAction
from .adapter import LegacyUIAdapter
from .buttons import ButtonSpec
from .models import (
    ChargeView,
    DiagnosticsView,
    JournalView,
    RuntimeUISnapshot,
    SafetyView,
    TelemetryView,
    TransitionView,
)
from .screen import (
    REQUIRED_SCREEN_FIELDS,
    ScreenId,
    ScreenSpec,
    missing_charge_screen_fields,
)

__all__ = [
    "ButtonSpec",
    "ChargeView",
    "DiagnosticsView",
    "JournalView",
    "LegacyUIAdapter",
    "REQUIRED_SCREEN_FIELDS",
    "RuntimeUISnapshot",
    "SafetyView",
    "ScreenId",
    "ScreenSpec",
    "TelemetryView",
    "TransitionView",
    "UIAction",
    "missing_charge_screen_fields",
]
