"""Process-lifetime fail-closed interlock after ambiguous link restoration.

The policy is deliberately sticky: only an explicit operator rearm may clear
it, and callers must first establish confirmed Output OFF. Persistence across
process restart is not provided by this owner.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RecoveryGuardState:
    quarantined: bool = False
    reason: str | None = None


class SessionRecoveryGuard:
    def __init__(self) -> None:
        self._state = RecoveryGuardState()

    @property
    def state(self) -> RecoveryGuardState:
        return self._state

    @property
    def quarantined(self) -> bool:
        return self._state.quarantined

    def quarantine(self, reason: str) -> RecoveryGuardState:
        if not self._state.quarantined:
            self._state = RecoveryGuardState(True, str(reason))
        return self._state

    def may_run_automatic_control(self) -> bool:
        return not self._state.quarantined

    def operator_rearm(self, *, confirmed_output_off: bool) -> bool:
        """Clear only on an explicit operator action with positive OFF proof."""
        if not confirmed_output_off:
            return False
        self._state = RecoveryGuardState()
        return True


__all__ = ["RecoveryGuardState", "SessionRecoveryGuard"]
