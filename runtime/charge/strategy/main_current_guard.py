"""Pure, acknowledgement-gated MAIN current-limit ratchet.

This module computes proposals only. It has no clock, persistence or hardware
adapter; callers supply timestamps and must commit only after independent fresh
set-current and OCP readbacks.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Any, Mapping


SCHEMA_VERSION = 1
HARDWARE_CURRENT_FLOOR_A = 0.1
SOFTWARE_CURRENT_MAX_A = 12.0
RATCHET_INTERVAL_S = 1800.0
CURRENT_HEADROOM_A = 1.0
EXPECTED_OCP_HEADROOM_A = 0.1
READBACK_TOLERANCE_A = 0.02
ACK_TIMEOUT_S = 120.0


class GuardError(ValueError):
    """Invalid, stale, mismatched, or unsafe guard state/input."""


@dataclass(frozen=True)
class PendingProposal:
    proposal_id: str
    target_limit_a: float
    created_at_s: float
    deadline_s: float


@dataclass(frozen=True)
class MainCurrentGuard:
    session_id: str
    battery_id: str
    segment_id: str
    capacity_ah: float
    recipe_initial_current_a: float
    initial_limit_a: float
    hardware_limit_a: float
    accrued_output_on_s: float = 0.0
    last_observed_at_s: float | None = None
    last_output_on: bool | None = None
    last_stage_main: bool = False
    proposal_sequence: int = 0
    pending: PendingProposal | None = None
    fault: str | None = None

    @classmethod
    def start(cls, *, session_id: str, battery_id: str, segment_id: str,
              capacity_ah: float, recipe_initial_current_a: float,
              now_s: float | None = None) -> "MainCurrentGuard":
        cap, recipe = _positive(capacity_ah, "capacity"), _positive(recipe_initial_current_a, "recipe current")
        initial = min(recipe, 0.10 * cap, SOFTWARE_CURRENT_MAX_A)
        if initial < HARDWARE_CURRENT_FLOOR_A:
            raise GuardError("initial current is below hardware floor")
        if not session_id or not battery_id or not segment_id:
            raise GuardError("session, battery and segment identity are required")
        return cls(session_id, battery_id, segment_id, cap, recipe, initial, initial,
                   last_observed_at_s=_time(now_s) if now_s is not None else None)

    @property
    def next_deadline_s(self) -> float:
        if self.pending:
            return self.pending.deadline_s
        return max(0.0, RATCHET_INTERVAL_S - self.accrued_output_on_s)

    def observe(self, *, now_s: float, output_on: bool, measured_current_a: float | None,
                fresh: bool, stage: str = "MAIN", desulfation_return_to_main: bool = False,
                battery_id: str | None = None, fault: str | None = None) -> tuple["MainCurrentGuard", PendingProposal | None]:
        now = _time(now_s)
        if type(output_on) is not bool or type(fresh) is not bool:
            return self._faulted("untrusted_output_or_freshness_type"), None
        main_stage = str(stage).upper() == "MAIN"
        if battery_id is not None and battery_id != self.battery_id:
            return self._faulted("battery_identity_changed"), None
        if fault:
            return self._faulted(f"external_fault:{fault}"), None
        if self.fault:
            return self, None
        if self.last_observed_at_s is not None and now < self.last_observed_at_s:
            return self._faulted("clock_rollback"), None
        if self.pending is not None:
            if now > self.pending.deadline_s:
                return self._faulted("proposal_ack_timeout"), None
            # Do not accrue or create another proposal while awaiting readback.
            return replace(self, last_observed_at_s=now,
                           last_output_on=bool(output_on and fresh and measured_current_a is not None),
                           last_stage_main=main_stage), None
        # Freshness is part of the ON-time proof, not merely a prerequisite
        # for making a proposal. A stale/unknown interval must break accrual.
        # Do not treat a remembered Output ON as evidence of current activity.
        evidenced_on = bool(output_on and fresh and measured_current_a is not None)
        elapsed = 0.0
        if (self.last_observed_at_s is not None and self.last_output_on
                and self.last_stage_main and main_stage and evidenced_on):
            elapsed = now - self.last_observed_at_s
        accrued = self.accrued_output_on_s + elapsed
        state = replace(self, accrued_output_on_s=accrued, last_observed_at_s=now,
                        last_output_on=evidenced_on, last_stage_main=main_stage)
        if desulfation_return_to_main:
            # A request is NOT proof that RD6018 was reprogrammed.
            # Only return_after_verified_desulfation() may authorize I0.
            return state._faulted("desulfation_return_requires_verified_hardware_restore"), None
        if str(stage).upper() != "MAIN" or not output_on or not fresh:
            return state, None
        if measured_current_a is None:
            return state, None
        current = _finite(measured_current_a, "measured current")
        if current < 0:
            return state._faulted("invalid_measured_current"), None
        if accrued < RATCHET_INTERVAL_S:
            return state, None
        target = min(self.hardware_limit_a, current + CURRENT_HEADROOM_A, self.initial_limit_a)
        if target >= self.hardware_limit_a - 1e-9:
            # No downward authority evidenced; consume this interval and wait again.
            return replace(state, accrued_output_on_s=accrued % RATCHET_INTERVAL_S), None
        if target < HARDWARE_CURRENT_FLOOR_A:
            return state._faulted("proposal_below_hardware_floor"), None
        seq = self.proposal_sequence + 1
        proposal = PendingProposal(f"{self.session_id}:{self.segment_id}:{seq}", target, now, now + ACK_TIMEOUT_S)
        return replace(state, proposal_sequence=seq, pending=proposal,
                       accrued_output_on_s=accrued % RATCHET_INTERVAL_S), proposal

    def commit(self, *, proposal_id: str, now_s: float, measured_current_a: float | None,
               measured_current_fresh: bool, current_limit_readback_a: float | None,
               current_readback_fresh: bool, ocp_limit_a: float | None,
               ocp_readback_fresh: bool) -> "MainCurrentGuard":
        pending = self.pending
        now = _time(now_s)
        if self.fault:
            return self
        if pending is None or pending.proposal_id != proposal_id:
            return self._faulted("ambiguous_or_wrong_proposal_ack")
        if now < pending.created_at_s or now > pending.deadline_s:
            return self._faulted("proposal_ack_timeout_or_clock_rollback")
        try:
            current = _finite(measured_current_a, "measured current")
            current_limit = _finite(current_limit_readback_a, "current limit readback")
            ocp = _finite(ocp_limit_a, "OCP readback")
        except GuardError:
            return self._faulted("missing_or_invalid_readback")
        if not measured_current_fresh or not current_readback_fresh or not ocp_readback_fresh:
            return self._faulted("stale_readback")
        if current < 0:
            return self._faulted("invalid_output_current_readback")
        if abs(current_limit - pending.target_limit_a) > READBACK_TOLERANCE_A:
            return self._faulted("programmed_current_readback_mismatch")
        expected_ocp = pending.target_limit_a + EXPECTED_OCP_HEADROOM_A
        if abs(ocp - expected_ocp) > READBACK_TOLERANCE_A:
            return self._faulted("OCP_readback_mismatch")
        return replace(self, hardware_limit_a=pending.target_limit_a, pending=None,
                       last_observed_at_s=now)

    def return_after_verified_desulfation(
        self, *, now_s: float, from_stage: str, to_stage: str,
        output_off_proven: bool, current_readback_a: float | None,
        ocp_readback_a: float | None, readbacks_fresh: bool,
        segment_id: str,
    ) -> "MainCurrentGuard":
        """Start a new MAIN epoch only after safe reset of Iset/OCP.

        Caller owns the full protected physical transaction and durable session
        transition; this pure method merely certifies its readback evidence.
        """
        now = _time(now_s)
        if self.fault or self.pending is not None:
            return self._faulted("desulfation_return_while_unsafe")
        if self.last_observed_at_s is not None and now < self.last_observed_at_s:
            return self._faulted("clock_rollback")
        if (from_stage.upper() != "DESULFATION" or to_stage.upper() != "MAIN"
                or not segment_id or segment_id == self.segment_id
                or not output_off_proven or not readbacks_fresh):
            return self._faulted("desulfation_return_boundary_unproven")
        try:
            new_i = _finite(current_readback_a, "current readback")
            new_ocp = _finite(ocp_readback_a, "OCP readback")
        except GuardError:
            return self._faulted("desulfation_return_readback_unavailable")
        if (abs(new_i - self.initial_limit_a) > READBACK_TOLERANCE_A
                or abs(new_ocp - self.initial_limit_a - EXPECTED_OCP_HEADROOM_A)
                > READBACK_TOLERANCE_A):
            return self._faulted("desulfation_return_readback_mismatch")
        return replace(self, segment_id=segment_id, hardware_limit_a=self.initial_limit_a,
                       accrued_output_on_s=0.0, last_observed_at_s=now,
                       last_output_on=False, last_stage_main=True)

    def _faulted(self, reason: str) -> "MainCurrentGuard":
        return replace(self, pending=None, fault=self.fault or reason)

    def snapshot(self) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, "session_id": self.session_id,
                "battery_id": self.battery_id, "segment_id": self.segment_id,
                "capacity_ah": self.capacity_ah, "recipe_initial_current_a": self.recipe_initial_current_a,
                "initial_limit_a": self.initial_limit_a, "hardware_limit_a": self.hardware_limit_a,
                "accrued_output_on_s": self.accrued_output_on_s,
                "last_observed_at_s": self.last_observed_at_s, "last_output_on": self.last_output_on,
                "last_stage_main": self.last_stage_main,
                "proposal_sequence": self.proposal_sequence,
                "pending": None if self.pending is None else self.pending.__dict__.copy(),
                "fault": self.fault}

    @classmethod
    def restore(cls, raw: Mapping[str, Any], *, session_id: str, battery_id: str,
                now_s: float) -> "MainCurrentGuard":
        try:
            if raw.get("schema_version") != SCHEMA_VERSION:
                raise GuardError("unsupported snapshot schema")
            if raw["session_id"] != session_id or raw["battery_id"] != battery_id:
                raise GuardError("journal identity mismatch")
            now = _time(now_s)
            last = raw.get("last_observed_at_s")
            if last is not None and now < _time(last):
                raise GuardError("clock rollback on restore")
            pending_raw = raw.get("pending")
            pending = PendingProposal(**pending_raw) if pending_raw is not None else None
            state = cls(session_id=str(raw["session_id"]), battery_id=str(raw["battery_id"]),
                        segment_id=str(raw["segment_id"]), capacity_ah=_positive(raw["capacity_ah"], "capacity"),
                        recipe_initial_current_a=_positive(raw["recipe_initial_current_a"], "recipe current"),
                        initial_limit_a=_positive(raw["initial_limit_a"], "initial limit"),
                        hardware_limit_a=_positive(raw["hardware_limit_a"], "hardware limit"),
                        accrued_output_on_s=_finite(raw["accrued_output_on_s"], "accrued time"),
                        last_observed_at_s=_time(last) if last is not None else None,
                        last_output_on=raw.get("last_output_on"), last_stage_main=raw.get("last_stage_main", False),
                        proposal_sequence=int(raw["proposal_sequence"]),
                        pending=pending, fault=raw.get("fault"))
            expected = min(state.recipe_initial_current_a, 0.10 * state.capacity_ah, SOFTWARE_CURRENT_MAX_A)
            if abs(expected - state.initial_limit_a) > 1e-6 or state.hardware_limit_a > state.initial_limit_a + 1e-6:
                raise GuardError("snapshot current bounds invalid")
            if state.accrued_output_on_s < 0 or state.accrued_output_on_s >= RATCHET_INTERVAL_S:
                raise GuardError("snapshot accrued time invalid")
            if type(state.last_stage_main) is not bool or state.last_output_on not in (None, True, False):
                raise GuardError("invalid saved stage/output state")
            if state.hardware_limit_a < HARDWARE_CURRENT_FLOOR_A:
                raise GuardError("snapshot below hardware floor")
            # A process restart creates an unknown interval. Preserve accrued
            # time and cap, but require a fresh observation before accruing again.
            return replace(state, last_output_on=False)
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, GuardError):
                raise
            raise GuardError("malformed snapshot") from exc


def _finite(value: Any, name: str) -> float:
    try:
        if isinstance(value, bool):
            raise GuardError(f"invalid {name}")
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise GuardError(f"invalid {name}") from exc
    if not math.isfinite(result):
        raise GuardError(f"invalid {name}")
    return result


def _positive(value: Any, name: str) -> float:
    result = _finite(value, name)
    if result <= 0:
        raise GuardError(f"{name} must be positive")
    return result


def _time(value: Any) -> float:
    result = _finite(value, "time")
    if result < 0:
        raise GuardError("time must be nonnegative")
    return result


__all__ = ["ACK_TIMEOUT_S", "CURRENT_HEADROOM_A", "HARDWARE_CURRENT_FLOOR_A", "MainCurrentGuard",
           "PendingProposal", "RATCHET_INTERVAL_S", "SCHEMA_VERSION", "SOFTWARE_CURRENT_MAX_A", "GuardError"]
