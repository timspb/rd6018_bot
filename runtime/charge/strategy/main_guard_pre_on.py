"""Pure MAIN Guard pre-ON reconciliation of canonical journal and native RD registers.

No output commands, no acceptance of new charging authority. This evaluates
ONLY the Guard condition; all other START/safety/lease/thermal gates remain
independently mandatory. Production integration has NOT been installed.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

from rd6018_telemetry import (
    canonical_programmed_readback, finite_float, telemetry_freshness,
)
from .main_current_guard import (
    EXPECTED_OCP_HEADROOM_A, MainCurrentGuard, READBACK_TOLERANCE_A,
)
from .main_guard_session import GUARD_KEY, GuardJournalError, read_guard

NATIVE_GUARD_PRE_ON_KEYS = (
    "output_state_code_v2", "set_current_readback_v2",
    "ocp_readback_v2", "protection_code",
)
MAX_NATIVE_AGE_S = 10.0


@dataclass(frozen=True)
class GuardPreOnAssessment:
    status: str  # NOT_APPLICABLE, RECONCILED, or BLOCKED
    reason: str
    journal_revision: int | None = None
    confirmed_ceiling_a: float | None = None

    @property
    def guard_reconciled(self) -> bool:
        return self.status == "RECONCILED"

    @property
    def is_guarded(self) -> bool:
        return self.status != "NOT_APPLICABLE"


def assess_main_guard_before_output_on(
    *,
    session_document: Mapping[str, Any],
    restored_guard: MainCurrentGuard | None,
    native_live: Mapping[str, Any],
    session_id: str,
    battery_id: str,
    profile: str,
    stage: str,
    target_current_a: float,
    owner_authorized: bool,
    edge_lease_armed: bool,
    now_epoch_s: float,
) -> GuardPreOnAssessment:
    """Inspect a previously guarded MAIN resume, never grant Output ON.

    A guarded session is RECONCILED only if live Output is OFF and the native
    Iset/OCP programming already equals the target not exceeding its persisted
    monotone ceiling. Any needed programming is a separate owner-owned OFF
    transaction, followed by a NEW fresh assessment before ON.
    """
    def blocked(reason: str) -> GuardPreOnAssessment:
        return GuardPreOnAssessment("BLOCKED", reason)

    if not isinstance(session_document, Mapping):
        return blocked("canonical_document_missing")
    recorded = GUARD_KEY in session_document
    if not recorded:
        if restored_guard is not None:
            return blocked("in_memory_guard_has_no_canonical_journal")
        return GuardPreOnAssessment("NOT_APPLICABLE", "no_main_guard_journal")
    if restored_guard is None:
        return blocked("guard_journal_was_not_restored")
    if not isinstance(native_live, Mapping):
        return blocked("native_snapshot_missing")
    if (owner_authorized is not True or edge_lease_armed is not True):
        return blocked("execution_owner_or_lease_unproven")
    if str(stage) != "Main Charge" or session_document.get("stage") != "Main Charge":
        return blocked("guarded_resume_requires_main_stage")
    if str(profile).strip().upper() not in {"EFB", "CA/CA"}:
        return blocked("guarded_profile_not_eligible")
    if str(session_document.get("profile")).strip().upper() != str(profile).strip().upper():
        return blocked("chemistry_changed_since_checkpoint")
    if session_document.get("v2_trace_session_id") != session_id:
        return blocked("session_identity_changed")
    if session_document.get("v2_battery_id") != battery_id:
        return blocked("battery_identity_changed")
    try:
        now = float(now_epoch_s)
        proposed = float(target_current_a)
    except (ValueError, TypeError, OverflowError):
        return blocked("invalid_clock_or_requested_current")
    if (not math.isfinite(now) or now <= 0 or not math.isfinite(proposed)
            or proposed <= 0):
        return blocked("invalid_clock_or_requested_current")
    try:
        saved, revision = read_guard(
            session_document,
            session_id=session_id,
            battery_id=battery_id,
            now_s=now,
        )
    except (GuardJournalError, ValueError, TypeError, OverflowError) as exc:
        return blocked("guard_checkpoint_not_trustworthy:" + type(exc).__name__)
    if (saved.fault is not None or saved.pending is not None
            or restored_guard.fault is not None or restored_guard.pending is not None):
        return blocked("unresolved_pending_or_faulted_guard")
    if (saved.session_id != restored_guard.session_id
            or saved.battery_id != restored_guard.battery_id
            or saved.segment_id != restored_guard.segment_id
            or saved.proposal_sequence != restored_guard.proposal_sequence
            or abs(saved.hardware_limit_a - restored_guard.hardware_limit_a) > 1e-9
            or abs(saved.initial_limit_a - restored_guard.initial_limit_a) > 1e-9
            or abs(saved.capacity_ah - restored_guard.capacity_ah) > 1e-9
            or abs(saved.recipe_initial_current_a - restored_guard.recipe_initial_current_a) > 1e-9):
        return blocked("live_guard_and_canonical_journal_disagree")
    if proposed > saved.hardware_limit_a + READBACK_TOLERANCE_A:
        return blocked("restore_target_exceeds_saved_main_ceiling")
    meta = native_live.get("_meta")
    if not isinstance(meta, Mapping):
        return blocked("native_freshness_metadata_missing")
    freshness = telemetry_freshness(
        native_live, NATIVE_GUARD_PRE_ON_KEYS,
        max_age_s=MAX_NATIVE_AGE_S, max_skew_s=MAX_NATIVE_AGE_S,
        now_epoch_s=now,
    )
    if not freshness.valid:
        return blocked("native_sources_stale_or_skewed")
    output_code = finite_float(native_live.get("output_state_code_v2"))
    protection_code = finite_float(native_live.get("protection_code"))
    if output_code != 0:
        return blocked("output_not_independently_verified_off")
    if protection_code != 0:
        return blocked("native_protection_not_normal")
    programmed_i = canonical_programmed_readback(native_live, "set_current")
    programmed_ocp = canonical_programmed_readback(native_live, "ocp")
    if programmed_i is None or programmed_ocp is None:
        return blocked("native_programmed_readback_unavailable")
    if programmed_i > saved.hardware_limit_a + READBACK_TOLERANCE_A:
        return blocked("physical_iset_exceeds_persisted_ceiling")
    if abs(programmed_i - proposed) > READBACK_TOLERANCE_A:
        return blocked("physical_iset_does_not_match_resume_target")
    if abs(programmed_ocp - programmed_i - EXPECTED_OCP_HEADROOM_A) > READBACK_TOLERANCE_A:
        return blocked("physical_ocp_not_confirmed")
    return GuardPreOnAssessment(
        "RECONCILED", "native_programming_matches_canonical_main_guard",
        journal_revision=revision,
        confirmed_ceiling_a=saved.hardware_limit_a,
    )


__all__ = [
    "GuardPreOnAssessment", "MAX_NATIVE_AGE_S",
    "NATIVE_GUARD_PRE_ON_KEYS", "assess_main_guard_before_output_on",
]
