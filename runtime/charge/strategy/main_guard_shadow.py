"""Production-owned, observation-only holder for the MAIN current guard.

This adapter deliberately has no hardware or filesystem dependencies. Persistence
is left to a future session owner with an explicit authorization boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .main_current_guard import MainCurrentGuard, PendingProposal


@dataclass
class MainGuardShadow:
    guard: MainCurrentGuard | None = None
    proposal: PendingProposal | None = None

    @classmethod
    def restore(cls, snapshot: dict[str, Any], *, session_id: str,
                battery_id: str, now_s: float) -> "MainGuardShadow":
        """Restore only a caller-validated canonical guard snapshot."""
        guard = MainCurrentGuard.restore(
            snapshot, session_id=session_id, battery_id=battery_id, now_s=now_s
        )
        return cls(guard=guard, proposal=guard.pending)

    def observe(self, *, now_s: float, session_id: str | None, battery_id: str | None,
                chemistry: str, capacity_ah: float, recipe_current_a: float,
                stage: str, output_on: bool | None, output_current_a: float | None,
                fresh: bool, owner_allows_persistence: bool = False,
                persistence: Any = None) -> PendingProposal | None:
        """Observe one accepted MAIN sample; never actuates or writes by default."""
        chem = str(chemistry).strip().upper()
        if chem not in {"EFB", "CA/CA", "CA_CA"}:
            return self.proposal
        # Record every non-MAIN observation in an already-bound epoch so that
        # even a short cooling/desulfation excursion breaks active-time
        # continuity. Never create a guard outside MAIN.
        if str(stage).upper() != "MAIN":
            if self.guard is not None and session_id == self.guard.session_id and battery_id == self.guard.battery_id:
                self.guard, _ = self.guard.observe(
                    now_s=now_s, output_on=output_on if type(output_on) is bool else False,
                    measured_current_a=output_current_a, fresh=bool(fresh) and type(output_on) is bool,
                    stage=stage, battery_id=battery_id,
                )
            return self.proposal
        # A genuine accepted session identity is mandatory. Missing identity is
        # a no-op; never synthesize IDs or silently start a new epoch.
        if not session_id or not battery_id or output_on is None:
            # Unknown Output evidence is not an unobserved gap that may be
            # joined by the next valid sample. Break the active interval.
            if self.guard is not None and session_id == self.guard.session_id and battery_id == self.guard.battery_id:
                self.guard, _ = self.guard.observe(
                    now_s=now_s, output_on=False, measured_current_a=None,
                    fresh=False, stage=stage, battery_id=battery_id,
                )
            return self.proposal
        if self.guard is None:
            try:
                self.guard = MainCurrentGuard.start(
                    session_id=session_id, battery_id=battery_id,
                    segment_id=f"{session_id}:MAIN", capacity_ah=capacity_ah,
                    recipe_initial_current_a=recipe_current_a, now_s=now_s,
                )
            except (TypeError, ValueError):
                return self.proposal
        elif self.guard.session_id != session_id or self.guard.battery_id != battery_id:
            # Do not silently reinitialize across a session boundary.
            return self.proposal
        self.guard, proposed = self.guard.observe(
            now_s=now_s, output_on=output_on, measured_current_a=output_current_a,
            fresh=bool(fresh), stage=stage, battery_id=battery_id,
        )
        if proposed is not None:
            self.proposal = proposed
        # No production owner currently grants journal-write permission. Keep
        # the explicit hook inert unless a future caller supplies an owner.
        if owner_allows_persistence and persistence is not None:
            persistence(self.guard)
        return self.proposal


__all__ = ["MainGuardShadow"]
