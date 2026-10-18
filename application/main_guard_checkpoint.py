"""Canonical one-owner, one-file MAIN Guard pending/ACK durability adapter.

No independently owned database or background task. Executed only *inside*
the existing GuardExecutionOwnerLock by the already existing ExecutionPort
MAIN current/OCP reduction transaction.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import time
from typing import Any, Callable

from application.guard_execution_owner_lock import GuardExecutionOwnerLock
from runtime.charge.session_atomic import atomic_session_write, complete_session_document
from runtime.charge.strategy.main_current_guard import MainCurrentGuard
from runtime.charge.strategy.main_guard_session import (
    GUARD_KEY, GuardJournalError, read_guard,
)

class MainGuardCheckpointError(RuntimeError):
    pass


class CanonicalMainGuardCheckpoint:
    """Write pending and post-readback ACK in the existing charge_session.json.

    The lock must already be held across preflight, hardware Iset/OCP and the
    two durable writes. A stale/missing/conflicting journal never gets silently
    reset. No caller other than the charge runtime should own this instance.
    """

    def __init__(self, *, controller: Any, owner_lock: GuardExecutionOwnerLock,
                 path: str | Path = "charge_session.json",
                 epoch_now: Callable[[], float] = time.time,
                 monotonic_now: Callable[[], float] = time.monotonic):
        self.controller = controller
        self.owner_lock = owner_lock
        self.path = Path(path)
        self.epoch_now = epoch_now
        self.monotonic_now = monotonic_now

    async def persist(self, snapshot: dict[str, Any]) -> None:
        if (not isinstance(self.owner_lock, GuardExecutionOwnerLock)
                or self.owner_lock.owner_task is not asyncio.current_task()
                or not self.owner_lock.locked()):
            raise MainGuardCheckpointError("canonical_execution_owner_lock_required")
        if self.path.is_symlink() or not self.path.is_file():
            raise MainGuardCheckpointError("canonical_session_missing_or_symlink")
        try:
            existing = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise MainGuardCheckpointError("canonical_session_unreadable") from exc
        if type(existing) is not dict or existing.get("state") == "retired":
            raise MainGuardCheckpointError("not_an_active_canonical_session")
        host = self.controller
        sid = getattr(host, "_v2_trace_session_id", None)
        bid = getattr(host, "_v2_battery_id", None)
        if (not sid or not bid or existing.get("v2_trace_session_id") != sid
                or existing.get("v2_battery_id") != bid
                or existing.get("stage") != getattr(host, "STAGE_MAIN", None)
                or getattr(host, "current_stage", None) != getattr(host, "STAGE_MAIN", None)
                or str(getattr(host, "battery_type", "")).upper() not in ("EFB", "CA/CA")
                or existing.get("profile") != getattr(host, "battery_type", None)
                or existing.get("v2_authoritative") is not True
                or existing.get("v2_trace_started_at") != getattr(host, "_v2_trace_started_at", None)
                or existing.get("ah_limit") != getattr(host, "ah_capacity", None)):
            raise MainGuardCheckpointError("canonical_main_session_identity_changed")
        now_epoch = float(self.epoch_now())
        saved = existing.get("saved_at")
        if (type(saved) not in (int, float) or saved > now_epoch
                or now_epoch - saved > 120.0):
            raise MainGuardCheckpointError("canonical_main_session_stale")
        state = MainCurrentGuard.restore(
            snapshot, session_id=str(sid), battery_id=str(bid),
            now_s=float(self.monotonic_now()),
        )
        if state.fault is not None:
            raise MainGuardCheckpointError("faulted_guard_cannot_claim_authority")
        if GUARD_KEY in existing:
            original, _ = read_guard(existing, session_id=sid, battery_id=bid,
                                     now_s=float(self.monotonic_now()))
            if original.segment_id != state.segment_id:
                raise MainGuardCheckpointError("main_segment_changed_without_verified_transition")
        old_current = getattr(host, "_main_current_guard", None)
        old_revision = getattr(host, "_main_current_guard_revision", None)
        host._main_current_guard = state
        try:
            next_doc = dict(existing)
            next_doc["saved_at"] = now_epoch
            # The current has changed physically ONLY after hardware ACK, but
            # pending always has the old limit. A stored physical current is
            # never raised by the Guard checkpoint writer.
            previous_target = existing.get("target_current")
            if (isinstance(previous_target, bool)
                    or type(previous_target) not in (int, float)
                    or abs(float(previous_target)-(
                        original.hardware_limit_a if GUARD_KEY in existing
                        else state.initial_limit_a)) > .02):
                raise MainGuardCheckpointError("canonical_current_preimage_disagrees")
            next_doc["target_current"] = state.hardware_limit_a
            next_doc = complete_session_document(host, next_doc,
                                                 previous=existing, now_s=now_epoch)
            atomic_session_write(self.path, next_doc, allow_nan=False)
            stored = json.loads(self.path.read_text(encoding="utf-8"))
            recorded, revision = read_guard(
                stored, session_id=sid, battery_id=bid,
                now_s=float(self.monotonic_now()))
            if (recorded.hardware_limit_a != state.hardware_limit_a
                    or recorded.proposal_sequence != state.proposal_sequence
                    or recorded.pending != state.pending):
                raise MainGuardCheckpointError("canonical_guard_postwrite_mismatch")
            host._main_current_guard_revision = revision
            # Other controller fields are not modified here. The caller still
            # owns actuator readback and terminal state transitions.
        except BaseException:
            # If a durable journal matching the newly attempted snapshot
            # exists, keep its in-memory ceiling even if readback failed.
            # An unreadable/ambiguous disk is also treated conservatively as
            # possibly committed; do not silently restore wider authority.
            committed_or_ambiguous = True
            try:
                disk = json.loads(self.path.read_text(encoding="utf-8"))
                disk_snapshot = disk.get(GUARD_KEY, {}).get("snapshot")
                committed_or_ambiguous = disk_snapshot == snapshot
            except (OSError, ValueError, AttributeError, TypeError):
                pass
            if not committed_or_ambiguous:
                host._main_current_guard = old_current
                host._main_current_guard_revision = old_revision
            raise


__all__ = ["MainGuardCheckpointError", "CanonicalMainGuardCheckpoint"]
