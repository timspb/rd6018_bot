"""In-process recovery quarantine for an unconfirmed physical restore.

This application lifecycle decision owns *only* whether automatic recovery and
ordinary controller ticks are admitted. It cannot actuate hardware, clear the
edge lease, infer an Output state, or grant an automatic release.
"""

from __future__ import annotations

from dataclasses import dataclass

from runtime.charge.link_session_recovery import RecoveryRoute


@dataclass(frozen=True)
class RecoveryContainment:
    """Sticky, immutable record of the first ambiguous restore in this process."""

    route: RecoveryRoute | None = None
    failed_step: str | None = None

    @property
    def blocked(self) -> bool:
        return self.route is not None

    def deny(self, route: RecoveryRoute, failed_step: str | None) -> "RecoveryContainment":
        if route is RecoveryRoute.NONE:
            raise ValueError("cannot quarantine an absent recovery route")
        if self.blocked:
            return self
        return RecoveryContainment(route=route, failed_step=failed_step or "unconfirmed")


__all__ = ["RecoveryContainment"]
