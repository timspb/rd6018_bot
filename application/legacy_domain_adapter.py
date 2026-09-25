"""Explicit V2-domain compatibility seam for V3 shadow consumers."""

from __future__ import annotations

# The import is intentionally isolated here. V3-facing modules must depend on
# this named adapter, never on runtime.charge directly.
from runtime.charge import (  # noqa: F401
    BatteryProfile,
    ChargeEngine,
    DomainDecision,
    Measurements,
    ProfileRegistry,
    SessionManager,
    SessionSnapshot,
    StrategyRuntimeState,
)
from runtime.charge.strategy import ChargeStrategy  # noqa: F401


LEGACY_DOMAIN_OWNER = "V2 legacy domain compatibility"


__all__ = [
    "BatteryProfile", "ChargeEngine", "DomainDecision", "Measurements",
    "ProfileRegistry", "SessionManager", "SessionSnapshot",
    "StrategyRuntimeState", "ChargeStrategy", "LEGACY_DOMAIN_OWNER",
]
