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
    def __init__(self, *, persist_incident=None, durable: bool = False,
                 initial_state: RecoveryGuardState | None = None) -> None:
        self._state = initial_state or RecoveryGuardState()
        self._persist_incident = persist_incident
        self._durable = bool(durable)

    @property
    def state(self) -> RecoveryGuardState:
        return self._state

    @property
    def quarantined(self) -> bool:
        return self._state.quarantined

    def quarantine(self, reason: str) -> RecoveryGuardState:
        if not self._state.quarantined:
            self._state = RecoveryGuardState(True, str(reason))
            if self._persist_incident is not None:
                # Latch RAM first; persistence failure propagates while the
                # same process remains blocked.
                self._persist_incident(self._state.reason or "unknown")
        return self._state

    def may_run_automatic_control(self) -> bool:
        return not self._state.quarantined

    def operator_rearm(self, *, confirmed_output_off: bool) -> bool:
        """Clear only on an explicit operator action with positive OFF proof."""
        if self._durable:
            return False
        if not confirmed_output_off:
            return False
        self._state = RecoveryGuardState()
        return True

    def _release_after_durable_retirement(self) -> None:
        """Coordinator-only final step after controller and journal commits."""
        self._state = RecoveryGuardState()


__all__ = ["RecoveryGuardState", "SessionRecoveryGuard"]
