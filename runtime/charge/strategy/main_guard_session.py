"""Versioned MAIN Guard checkpoint in the canonical charge-session document.

No hardware I/O, no controller mutation. The production charge_session.json
writer must be migrated to share ONE owner lock before enabling this adapter.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from .main_current_guard import MainCurrentGuard, GuardError, READBACK_TOLERANCE_A

GUARD_KEY = "main_current_guard_v1"
JOURNAL_SCHEMA = 1
ELIGIBLE_STAGES = frozenset({
    "Main Charge", "Охлаждение", "Десульфатация", "Безопасное ожидание",
    # A sealed, existing MAIN journal can continue into final MIX. It does
    # not grant fresh MAIN Guard authority to a MIX-only session.
    "Mix Mode",
})


class GuardJournalError(ValueError):
    pass


def _digest(snapshot: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _identity(document: Mapping[str, Any], guard: MainCurrentGuard) -> None:
    if document.get("v2_trace_session_id") != guard.session_id:
        raise GuardJournalError("session_identity_mismatch")
    if document.get("v2_battery_id") != guard.battery_id:
        raise GuardJournalError("battery_identity_mismatch")
    stage = document.get("stage")
    if stage == "Done":
        # Terminal Storage retains the prior MAIN Guard journal, but is not
        # another MAIN current-limit authority. Also preserve terminal OFF
        # evidence without replacing or erasing the existing guarded history.
        from runtime.charge.terminal_intent import (
            DONE_COMPLETION_STORAGE, DONE_COMPLETION_TERMINAL,
            DONE_OUTPUT_ON, DONE_OUTPUT_OFF,
        )
        terminal_shape = (
            document.get("done_state_version") == 1
            and document.get("terminal_session_id") == guard.session_id
            and (document.get("completion_kind"), document.get("output_intent"))
            in {
                (DONE_COMPLETION_STORAGE, DONE_OUTPUT_ON),
                (DONE_COMPLETION_TERMINAL, DONE_OUTPUT_OFF),
            }
        )
        if not terminal_shape:
            raise GuardJournalError("terminal_guard_intent_invalid")
    elif stage not in ELIGIBLE_STAGES:
        raise GuardJournalError("ineligible_charge_stage")
    try:
        capacity = float(document["ah_limit"])
    except (KeyError, ValueError, TypeError):
        raise GuardJournalError("capacity_unavailable") from None
    if not math.isfinite(capacity) or abs(capacity - guard.capacity_ah) > 1e-6:
        raise GuardJournalError("capacity_identity_mismatch")
    if str(document.get("profile")).strip().upper() not in {"EFB", "CA/CA"}:
        raise GuardJournalError("not_efb_ca_ca")


def read_guard(document: Mapping[str, Any], *, session_id: str,
               battery_id: str, now_s: float) -> tuple[MainCurrentGuard, int]:
    if not isinstance(document, Mapping):
        raise GuardJournalError("session_not_mapping")
    record = document.get(GUARD_KEY)
    if not isinstance(record, Mapping):
        raise GuardJournalError("guard_journal_absent")
    if record.get("journal_schema") != JOURNAL_SCHEMA:
        raise GuardJournalError("journal_schema_invalid")
    version = record.get("revision")
    if type(version) is not int or version <= 0:
        raise GuardJournalError("journal_revision_invalid")
    snapshot = record.get("snapshot")
    if not isinstance(snapshot, Mapping):
        raise GuardJournalError("snapshot_not_mapping")
    try:
        digest = _digest(snapshot)
    except (TypeError, ValueError, OverflowError) as exc:
        raise GuardJournalError("unserializable_guard_snapshot") from exc
    if digest != record.get("sha256"):
        raise GuardJournalError("guard_integrity_mismatch")
    try:
        guard = MainCurrentGuard.restore(
            snapshot, session_id=session_id, battery_id=battery_id, now_s=now_s
        )
    except GuardError as exc:
        raise GuardJournalError("invalid_guard_snapshot") from exc
    _identity(document, guard)
    return guard, version


def attach_guard(document: Mapping[str, Any], guard: MainCurrentGuard, *,
                 now_s: float, expected_revision: int) -> dict[str, Any]:
    """Prepare a single atomic JSON write with session and guard together.

    No epoch reauthorization happens here: an upward reset or erased pending
    proposal requires the future validated desulfation transaction owner.
    """
    if type(expected_revision) is not int or expected_revision < 0:
        raise GuardJournalError("expected_revision_invalid")
    _identity(document, guard)
    previous = document.get(GUARD_KEY)
    if document.get("stage") == "Done" and (
        previous is None or expected_revision <= 0
    ):
        raise GuardJournalError("terminal_requires_existing_main_guard")
    if document.get("stage") == "Mix Mode":
        # MIX can preserve an already-validated, revisioned MAIN Guard but
        # cannot create or erase its ratchet journal on its own.
        if previous is None or expected_revision <= 0:
            raise GuardJournalError("mix_requires_existing_main_guard")
        if guard.pending is not None:
            raise GuardJournalError("mix_requires_resolved_main_guard")
    if previous is None:
        if expected_revision != 0:
            raise GuardJournalError("missing_existing_guard_checkpoint")
        revision = 1
    else:
        old, old_revision = read_guard(
            document, session_id=guard.session_id,
            battery_id=guard.battery_id, now_s=now_s,
        )
        if old_revision != expected_revision:
            raise GuardJournalError("stale_canonical_checkpoint_revision")
        if guard.segment_id != old.segment_id:
            verified_return_shape = (
                document.get("stage") == "Безопасное ожидание"
                and guard.fault is None and guard.pending is None
                and guard.hardware_limit_a == guard.initial_limit_a
                and guard.accrued_output_on_s == 0.0
                and guard.last_output_on is False and guard.last_stage_main is True
                and guard.last_observed_at_s is not None
            )
            interrupted_return_compensation = (
                document.get("stage") == "Безопасное ожидание"
                and guard.fault is None and guard.pending is None
                and guard.hardware_limit_a <= old.hardware_limit_a
                and guard.accrued_output_on_s == 0.0
                and guard.last_output_on is False and guard.last_stage_main is True
                and guard.last_observed_at_s is not None
            )
            if not (verified_return_shape or interrupted_return_compensation):
                raise GuardJournalError("new_main_epoch_requires_verified_desulfation_return")
        verified_return = (
            guard.segment_id != old.segment_id
            and document.get("stage") == "Безопасное ожидание"
            and guard.hardware_limit_a == guard.initial_limit_a
            and old.hardware_limit_a < guard.hardware_limit_a
        )
        if (guard.hardware_limit_a > old.hardware_limit_a + READBACK_TOLERANCE_A
                and not verified_return):
            raise GuardJournalError("guard_ceiling_cannot_be_enlarged")
        if guard.proposal_sequence < old.proposal_sequence:
            raise GuardJournalError("proposal_sequence_rollback")
        if old.pending is not None and guard.pending is not None and guard.pending != old.pending:
            raise GuardJournalError("pending_proposal_substitution")
        if old.pending is not None and guard.pending is None:
            valid_committed = (
                guard.hardware_limit_a <= old.pending.target_limit_a + READBACK_TOLERANCE_A
                and guard.hardware_limit_a < old.hardware_limit_a
            )
            if not valid_committed and not guard.fault:
                raise GuardJournalError("pending_proposal_cannot_disappear")
        revision = old_revision + 1
    snapshot = guard.snapshot()
    if not math.isfinite(float(now_s)) or now_s < 0:
        raise GuardJournalError("invalid_checkpoint_clock")
    # Validate OUR snapshot as strictly as a restored one. This prohibits
    # invalid values being durably blessed during the initial write.
    try:
        MainCurrentGuard.restore(
            snapshot, session_id=guard.session_id,
            battery_id=guard.battery_id,
            now_s=max(float(now_s), float(snapshot.get("last_observed_at_s") or 0)),
        )
    except GuardError as exc:
        raise GuardJournalError("invalid_new_guard_snapshot") from exc
    result = dict(document)
    result[GUARD_KEY] = {
        "journal_schema": JOURNAL_SCHEMA, "revision": revision,
        "snapshot": snapshot, "sha256": _digest(snapshot),
    }
    return result


def atomic_write_guard_session(path: Path, guard: MainCurrentGuard, *,
                               now_s: float, expected_revision: int) -> int:
    """Atomic replacement requiring EXCLUSIVE ownership by the caller.

    This is not a sidecar writer. Do not call while the legacy session writer
    runs independently; that writer must share the same owner lock first.
    """
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise GuardJournalError("canonical_session_not_object")
    except (OSError, json.JSONDecodeError) as exc:
        raise GuardJournalError("canonical_session_unavailable") from exc
    next_document = attach_guard(raw, guard, now_s=now_s,
                                 expected_revision=expected_revision)
    content = json.dumps(next_document, ensure_ascii=False, indent=2,
                         allow_nan=False).encode("utf-8") + b"\n"
    # Same-directory temporary file is required for atomic os.replace.
    fd, temporary = tempfile.mkstemp(prefix=".main-guard-", suffix=".tmp",
                                    dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return int(next_document[GUARD_KEY]["revision"])


__all__ = [
    "GUARD_KEY", "GuardJournalError", "read_guard", "attach_guard",
    "atomic_write_guard_session",
]