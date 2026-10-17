"""Fail-closed boundary for operator-approved recovery quarantine clearance.

No production authority, verified-OFF provenance, or durable session-retirement
provider currently implements these typed contracts. This coordinator stays
unwired until all three owners exist.
"""
from __future__ import annotations

import time
import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AuthorizedRecoveryOperator:
    operator_id: str


@dataclass(frozen=True)
class VerifiedOffEvidence:
    transaction_id: str
    issued_monotonic: float


@dataclass(frozen=True)
class RetiredControllerSession:
    session_id: str


@dataclass(frozen=True)
class RecoveryClearanceResult:
    cleared: bool
    reason: str


class OperatorRecoveryClearanceService:
    """Staged coordinator. Inputs are typed receipts, never caller flags."""

    def __init__(self, *, execution_port: Any, journal: Any,
                 operator_authority: Any = None, session_retirement: Any = None) -> None:
        self._port = execution_port
        self._journal = journal
        self._authority = operator_authority
        self._retire_session = session_retirement

    async def clear(self, operator_context: Any) -> RecoveryClearanceResult:
        guard = self._port.session_recovery_guard
        lock = getattr(self._port, "_guard_owner_lock", None)
        if lock is None:
            return RecoveryClearanceResult(False, "canonical_owner_lock_unavailable")
        async with lock:
            if not guard.quarantined:
                return RecoveryClearanceResult(False, "not_quarantined")
            authorize = getattr(self._authority, "authorize_clearance", None)
            try:
                operator = authorize(operator_context) if callable(authorize) else None
            except Exception:
                operator = None
            if (not isinstance(operator, AuthorizedRecoveryOperator)
                    or not isinstance(operator.operator_id, str) or not operator.operator_id.strip()):
                return RecoveryClearanceResult(False, "operator_authority_unavailable_or_denied")
            session_id_fn = getattr(self._retire_session, "session_id", None)
            retire_fn = getattr(self._retire_session, "retire", None)
            if not callable(session_id_fn) or not callable(retire_fn):
                return RecoveryClearanceResult(False, "controller_session_retirement_unavailable")
            try:
                session_id = session_id_fn()
            except Exception:
                session_id = None
            if not isinstance(session_id, str) or not session_id.strip():
                return RecoveryClearanceResult(False, "session_identity_unavailable")
            # Bind exact incident and persisted session before any physical call.
            try:
                binding = self._journal.incident_binding()
                if binding["session_id"] != session_id or not self._retire_session.validate(binding):
                    return RecoveryClearanceResult(False, "incident_session_identity_mismatch")
                if getattr(operator_context, "incident_id", None) != binding["incident_id"]:
                    return RecoveryClearanceResult(False, "confirmation_incident_mismatch")
            except Exception:
                return RecoveryClearanceResult(False, "incident_identity_unavailable")
            try:
                evidence = await self._port.request_verified_off_evidence()
            except Exception:
                return RecoveryClearanceResult(False, "verified_off_failed")
            now = time.monotonic()
            if (not isinstance(evidence, VerifiedOffEvidence)
                    or not evidence.transaction_id.strip()
                    or not isinstance(evidence.issued_monotonic, (float, int))
                    or not math.isfinite(evidence.issued_monotonic)
                    or evidence.issued_monotonic > now
                    or now - evidence.issued_monotonic > 30.0):
                return RecoveryClearanceResult(False, "fresh_off_evidence_unavailable")
            try:
                retired = retire_fn(session_id, binding=binding, off_evidence=evidence)
            except Exception:
                return RecoveryClearanceResult(False, "session_retirement_failed")
            if not isinstance(retired, RetiredControllerSession) or retired.session_id != session_id:
                return RecoveryClearanceResult(False, "session_retirement_failed")
            try:
                self._journal.retire(operator_id=operator.operator_id, session_id=session_id,
                                     confirmed_off_evidence=evidence.transaction_id)
            except Exception:
                return RecoveryClearanceResult(False, "durable_retirement_failed")
            finalize = getattr(self._retire_session, "finalize", None)
            try:
                if callable(finalize):
                    finalize(session_id)
            except Exception:
                return RecoveryClearanceResult(False, "durable_retirement_finalize_failed")
            guard._release_after_durable_retirement()
            return RecoveryClearanceResult(True, "cleared")


__all__ = ["AuthorizedRecoveryOperator", "OperatorRecoveryClearanceService",
           "RecoveryClearanceResult", "RetiredControllerSession", "VerifiedOffEvidence"]
