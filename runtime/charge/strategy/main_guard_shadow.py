"""Production-owned, observation-only holder for the MAIN current guard.

This adapter deliberately has no hardware or filesystem dependencies. The
existing charge-session owner may reconcile its clock snapshot while holding
the ExecutionPort owner lock; all writes stay in the canonical session writer.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .main_current_guard import GuardError, MainCurrentGuard, PendingProposal


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

    def bind_new_canonical_session(self, *, session_id: str, battery_id: str,
                                   unguarded_document_proven: bool) -> bool:
        """Explicit owner-only epoch boundary for a genuinely NEW session.

        Call only after read-only admission checked the current durable
        session and proved it has no Guard journal/in-memory cap. This is
        not a way to reset the current ratchet or clear a pending ACK.
        """
        if (unguarded_document_proven is not True or not session_id
                or not battery_id or self.guard is None
                or (self.guard.session_id == session_id
                    and self.guard.battery_id == battery_id)):
            return False
        self.guard = None
        self.proposal = None
        return True

    def invalidate_evidence(self, *, now_s: float) -> None:
        """Break ON continuity if durable identity or native evidence is missing."""
        self.proposal = None
        if self.guard is not None:
            self.guard, _ = self.guard.observe(
                now_s=now_s, output_on=False, measured_current_a=None,
                fresh=False, stage="OTHER", battery_id=self.guard.battery_id,
            )
            # Revoking an externally visible proposal never clears a
            # pending hardware acknowledgement or expands the old ceiling.

    def seed_from_controller(self, controller: Any, *, session_id: str,
                             battery_id: str) -> bool:
        """Resume this process-local observer from the canonical owner state.

        Restored guards intentionally have ``last_output_on=False``. Copying
        that state keeps prior accrued time while requiring a fresh Native
        sample to establish a new continuity interval.
        """
        if self.guard is not None:
            return self.guard.session_id == session_id and self.guard.battery_id == battery_id
        guard = getattr(controller, "_main_current_guard", None)
        if (guard is None or guard.session_id != session_id
                or guard.battery_id != battery_id or guard.pending is not None
                or guard.fault is not None):
            return False
        self.guard = guard
        self.proposal = None
        return True

    def reconcile_checkpoint(self, controller: Any, *, session_id: str,
                             battery_id: str,
                             persisted_revision: int | None = None) -> bool:
        """Publish safe shadow clock state to the existing session writer.

        Caller holds the common ExecutionPort owner lock and has admitted the
        canonical session plus current Native Iset/OCP preimage. This never
        changes the ratcheted ceiling or moves a pending/faulted transaction.
        """
        shadow = self.guard
        current = getattr(controller, "_main_current_guard", None)
        if (shadow is None or shadow.session_id != session_id
                or shadow.battery_id != battery_id or shadow.pending is not None
                or shadow.fault is not None):
            return False
        if current is not None:
            if (current.session_id != session_id or current.battery_id != battery_id
                    or current.segment_id != shadow.segment_id
                    or current.pending is not None or current.fault is not None
                    or current.proposal_sequence != shadow.proposal_sequence
                    or current.hardware_limit_a != shadow.hardware_limit_a
                    or current.initial_limit_a != shadow.initial_limit_a
                    or current.recipe_initial_current_a != shadow.recipe_initial_current_a
                    or current.capacity_ah != shadow.capacity_ah
                    or persisted_revision != getattr(controller, "_main_current_guard_revision", None)
                    or (current.last_observed_at_s is not None
                        and (shadow.last_observed_at_s is None
                             or shadow.last_observed_at_s < current.last_observed_at_s))):
                return False
        # The controller owner receives the exact observed clock fields, while
        # immutable identity and ceiling remain those already owned by it.
        if current is not None:
            shadow = replace(
                shadow, session_id=current.session_id, battery_id=current.battery_id,
                segment_id=current.segment_id, capacity_ah=current.capacity_ah,
                recipe_initial_current_a=current.recipe_initial_current_a,
                initial_limit_a=current.initial_limit_a,
                hardware_limit_a=current.hardware_limit_a,
                proposal_sequence=current.proposal_sequence,
            )
            self.guard = shadow
        controller._main_current_guard = shadow
        return True

    def observe(self, *, now_s: float, session_id: str | None, battery_id: str | None,
                chemistry: str, capacity_ah: float, recipe_current_a: float,
                stage: str, output_on: bool | None, output_current_a: float | None,
                fresh: bool, owner_allows_persistence: bool = False,
                persistence: Any = None) -> PendingProposal | None:
        """Observe one accepted MAIN sample; never actuates or writes by default."""
        chem = str(chemistry).strip().upper()
        if chem not in {"EFB", "CA/CA", "CA_CA"}:
            # A proposal belongs to its original EFB/Ca/Ca MAIN session.
            # Never expose it when observing AGM or an unknown chemistry.
            return None
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
            return None
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
            return None
        if self.guard is None:
            try:
                self.guard = MainCurrentGuard.start(
                    session_id=session_id, battery_id=battery_id,
                    segment_id=f"{session_id}:MAIN", capacity_ah=capacity_ah,
                    recipe_initial_current_a=recipe_current_a, now_s=now_s,
                )
            except (TypeError, ValueError):
                return None
        elif self.guard.session_id != session_id or self.guard.battery_id != battery_id:
            # Do not silently reinitialize or disclose the old pending
            # proposal across a session/battery boundary.
            return None
        try:
            self.guard, proposed = self.guard.observe(
                now_s=now_s, output_on=output_on, measured_current_a=output_current_a,
                fresh=fresh is True, stage=stage, battery_id=battery_id,
            )
        except (GuardError, TypeError, ValueError):
            # A bad physical-current sample is never an actuator proposal or
            # permission to reset a previously tightened current ceiling.
            self.guard = self.guard._faulted("untrusted_main_current_sample")
            self.proposal = None
            return None
        self.proposal = self.guard.pending if self.guard.fault is None else None
        # No production owner currently grants journal-write permission. Keep
        # the explicit hook inert unless a future caller supplies an owner.
        if owner_allows_persistence and persistence is not None:
            persistence(self.guard)
        return self.proposal


__all__ = ["MainGuardShadow"]
