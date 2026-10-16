"""D076: read-only native evidence of an already committed MIX Iset cap.

This module NEVER sets a current, trips a PSU, or creates authority. The
committed receipt must come from an independently reconciled execution owner.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from typing import Any, Mapping


_NATIVE = ("output_state_code_v2", "regulation_code",
           "set_current_readback_v2", "current")
# RD6018 set-current register is published to 0.01 A resolution. This is
# observational agreement, not a calibrated adaptive headroom or trip margin.
_REGISTER_TOLERANCE_A = 0.01
_EVIDENCE_MAX_AGE_S = 20.0
_EVIDENCE_MAX_SKEW_S = 10.0


class ClipStatus(str, Enum):
    PROVED_CLIPPED = "proved_clipped"
    NOT_CLIPPED = "not_clipped"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CommittedMixCurrentCap:
    """Owner-supplied, POST-READBACK committed session authority, not a proposal."""
    session_id: str
    battery_id: str
    chemistry: str
    initial_ceiling_a: float
    acknowledged_limit_a: float
    acknowledged_at_epoch_s: float
    committed: bool


@dataclass(frozen=True)
class MixClipEvidence:
    status: ClipStatus
    reason: str

    def censor_cc_delta(self, *, adaptive_ratchet_active: bool) -> bool:
        # An unproven active ratchet must not create positive chemical Delta
        # evidence. No adaptive ratchet: preserve ordinary CC behavior.
        return self.status is ClipStatus.PROVED_CLIPPED or (
            adaptive_ratchet_active and self.status is ClipStatus.UNKNOWN
        )


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        val = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return val if isfinite(val) else None


def _timestamp(raw: Any) -> float | None:
    if not isinstance(raw, str):
        return None
    try:
        stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return None
        val = stamp.timestamp()
    except (TypeError, ValueError, OverflowError):
        return None
    return val if isfinite(val) else None


def _code(value: Any) -> int | None:
    val = _number(value)
    return int(val) if val is not None and val in (0.0, 1.0) else None


def classify_mix_current_clip(
    live: Mapping[str, Any],
    *, receipt: CommittedMixCurrentCap | None,
    session_id: str,
    battery_id: str,
    chemistry: str,
    now_epoch_s: float,
    previous_report_epoch_s: float | None = None,
) -> MixClipEvidence:
    """Classify genuine native CC at a committed LOWER MIX Iset authority.

    Requires fresh post-commit raw register 17, 18, 9 and current measurements,
    and a previous report cursor to reject repeated heartbeats.
    Uses no UI flags and does not equate ordinary CC with adaptive clipping.
    An invalid or untrusted receipt is UNKNOWN, never an automatic authority.
    """
    unknown = lambda reason: MixClipEvidence(ClipStatus.UNKNOWN, reason)
    chem = str(chemistry).strip().upper()
    if chem not in {"EFB", "CA/CA", "CA_CA"}:
        return MixClipEvidence(ClipStatus.NOT_CLIPPED, "chemistry_out_of_scope")
    if receipt is None:
        # Absence of a trusted owner receipt cannot be evidence of ordinary CC
        # when an adaptive ratchet was previously active.
        return unknown("no_committed_adaptive_cap")
    if not isinstance(receipt, CommittedMixCurrentCap) or receipt.committed is not True:
        return unknown("uncommitted_cap")
    if (not session_id or not battery_id
            or receipt.session_id != session_id or receipt.battery_id != battery_id
            or not isinstance(receipt.chemistry, str)
            or receipt.chemistry.strip().upper() != chem):
        return unknown("session_or_battery_mismatch")
    initial = _number(receipt.initial_ceiling_a)
    cap = _number(receipt.acknowledged_limit_a)
    accepted_at = _number(receipt.acknowledged_at_epoch_s)
    now = _number(now_epoch_s)
    last_seen = _number(previous_report_epoch_s)
    if last_seen is None:
        return unknown("no_previous_native_report_cursor")
    if now is None or last_seen > now or last_seen <= 0:
        return unknown("invalid_native_report_cursor")
    if (initial is None or cap is None or accepted_at is None or now is None
            or initial <= 0 or cap <= 0 or accepted_at <= 0
            or accepted_at > now
            or initial - cap <= _REGISTER_TOLERANCE_A + 1e-9):
        return unknown("cap_not_verified_tighter")
    if not isinstance(live, Mapping):
        return unknown("native_snapshot_missing")
    meta = live.get("_meta")
    if not isinstance(meta, Mapping):
        return unknown("native_metadata_missing")
    samples: dict[str, float] = {}
    identities: set[str] = set()
    for key in _NATIVE:
        entry = meta.get(key)
        if not isinstance(entry, Mapping):
            return unknown(f"native_metadata_missing:{key}")
        if str(entry.get("status", "ok")).lower() != "ok":
            return unknown(f"native_status_bad:{key}")
        # source_key is optional on raw HA entity metadata. If present, it
        # MUST identify the same native register; legacy aliases cannot pass.
        if "source_key" in entry and entry["source_key"] != key:
            return unknown(f"native_source_mismatch:{key}")
        # HA readbacks contain an entity_id; raw Modbus aliases may add
        # source_key. A mapped UI proxy or duplicated producer is not proof.
        identity = entry.get("entity_id") or entry.get("source_key")
        if not isinstance(identity, str) or not identity.strip():
            return unknown(f"native_identity_missing:{key}")
        if identity in identities:
            return unknown("native_producer_duplicate")
        identities.add(identity)
        stamp = _timestamp(entry.get("last_reported"))
        if stamp is None:
            return unknown(f"native_last_reported_missing:{key}")
        if stamp > now + 1.0 or now - stamp > _EVIDENCE_MAX_AGE_S:
            return unknown(f"native_stale_or_future:{key}")
        if stamp <= last_seen:
            return unknown(f"native_report_replayed:{key}")
        samples[key] = stamp
    if max(samples.values()) - min(samples.values()) > _EVIDENCE_MAX_SKEW_S:
        return unknown("native_epoch_skew")
    if min(samples.values()) < accepted_at - 1.0:
        return unknown("native_readback_precedes_commit")
    if _code(live.get("output_state_code_v2")) != 1:
        return unknown("output_not_proved_on")
    mode = _code(live.get("regulation_code"))
    if mode is None:
        return unknown("regulation_not_native")
    readback = _number(live.get("set_current_readback_v2"))
    measured = _number(live.get("current"))
    if readback is None or measured is None or measured <= 0:
        return unknown("current_or_iset_missing")
    if abs(readback - cap) > _REGISTER_TOLERANCE_A + 1e-9:
        return unknown("iset_not_at_committed_cap")
    if mode == 0:
        return MixClipEvidence(ClipStatus.NOT_CLIPPED, "native_cv")
    # Native register 17 confirms current regulation at the lowered, committed
    # limit. Current measurement is sanity-only, not an invented noise cutoff.
    return MixClipEvidence(ClipStatus.PROVED_CLIPPED, "native_cc_at_committed_iset")


__all__ = [
    "ClipStatus", "CommittedMixCurrentCap", "MixClipEvidence",
    "classify_mix_current_clip",
]
