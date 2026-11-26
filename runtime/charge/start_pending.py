"""Canonical START_PENDING envelope lifecycle for the charge session file."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from runtime.charge.session_atomic import (
    compare_delete_session,
    compare_replace_session,
)


SESSION_FILE = "charge_session.json"


START_PENDING_KEY = "start_transaction_pending_v1"


class StartPendingStatus(str, Enum):
    COMMITTED = "COMMITTED"
    NOT_COMMITTED = "NOT_COMMITTED"
    OUTCOME_UNCERTAIN = "OUTCOME_UNCERTAIN"


class StartPendingAction(str, Enum):
    COMMIT = "COMMIT"
    ROLLBACK = "ROLLBACK"


@dataclass(frozen=True)
class StartPendingResult:
    status: StartPendingStatus
    pending_raw: bytes | None = None
    pending: Mapping[str, Any] | None = None
    observed_raw: bytes | None = None
    reason: str | None = None


def _pending_start_document(document: Any) -> bool:
    return isinstance(document, dict) and any(
        str(key).startswith("start_transaction_") and key != "start_transaction_generation"
        for key in document
    )


def read_start_pending(path: str | Path = SESSION_FILE) -> tuple[bytes | None, Mapping[str, Any] | None, str | None]:
    """Return exact canonical bytes and a validated pending envelope, if present."""
    file = Path(path)
    try:
        raw = file.read_bytes()
    except FileNotFoundError:
        return None, None, None
    except OSError as exc:
        return None, None, f"canonical_read_failed:{type(exc).__name__}"
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError):
        return raw, None, "canonical_malformed"
    if not isinstance(doc, dict):
        return raw, None, "canonical_malformed"
    pending = doc.get(START_PENDING_KEY)
    if pending is None:
        return raw, None, None
    if (not isinstance(pending, dict) or pending.get("schema_version") != 1
            or pending.get("phase") != "START_PENDING"
            or type(pending.get("generation")) is not int
            or pending["generation"] <= 0
            or not isinstance(pending.get("transaction_id"), str)
            or not pending["transaction_id"]
            or not isinstance(pending.get("previous_raw_utf8"), str)
            or not isinstance(pending.get("previous_sha256"), str)
            or type(pending.get("previous_exists")) is not bool
            or type(pending.get("previous_generation")) is not int
            or not isinstance(pending.get("candidate_sha256"), str)):
        return raw, None, "start_pending_malformed"
    previous = pending["previous_raw_utf8"].encode("utf-8")
    if hashlib.sha256(previous).hexdigest() != pending["previous_sha256"]:
        return raw, None, "start_pending_previous_hash_mismatch"
    if not isinstance(pending.get("candidate"), dict):
        return raw, None, "start_pending_candidate_malformed"
    if pending["previous_exists"]:
        try:
            previous_doc = json.loads(previous.decode("utf-8"))
        except (UnicodeError, ValueError):
            return raw, None, "start_pending_previous_malformed"
        if not isinstance(previous_doc, dict) or _pending_start_document(previous_doc):
            return raw, None, "start_pending_previous_malformed"
        prior_generation = previous_doc.get("start_transaction_generation", 0)
        if (type(prior_generation) is not int
                or prior_generation != pending["previous_generation"]
                or pending["generation"] != prior_generation + 1):
            return raw, None, "start_pending_generation_mismatch"
    elif previous or pending["previous_generation"] != 0 or pending["generation"] != 1:
        return raw, None, "start_pending_generation_mismatch"
    try:
        candidate_bytes = json.dumps(
            pending["candidate"], ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        return raw, None, "start_pending_candidate_malformed"
    if hashlib.sha256(candidate_bytes).hexdigest() != pending["candidate_sha256"]:
        return raw, None, "start_pending_candidate_hash_mismatch"
    return raw, pending, None


def begin_start_pending(candidate: Mapping[str, Any], *, transaction_id: str,
                        path: str | Path = SESSION_FILE) -> StartPendingResult:
    """Durably write the START intent in the sole canonical document."""
    if not isinstance(transaction_id, str) or not transaction_id.strip():
        return StartPendingResult(StartPendingStatus.NOT_COMMITTED, reason="transaction_id_required")
    prior_raw, pending, error = read_start_pending(path)
    if error or pending is not None:
        return StartPendingResult(StartPendingStatus.OUTCOME_UNCERTAIN if error
                                  else StartPendingStatus.NOT_COMMITTED, reason=error or "pending_exists")
    try:
        prior_doc = json.loads(prior_raw.decode("utf-8")) if prior_raw is not None else None
    except (UnicodeError, ValueError):
        return StartPendingResult(StartPendingStatus.NOT_COMMITTED, reason="prior_malformed")
    if prior_doc is not None and not isinstance(prior_doc, dict):
        return StartPendingResult(StartPendingStatus.NOT_COMMITTED, reason="prior_not_object")
    generation = 1
    if isinstance(prior_doc, dict):
        prior_gen = prior_doc.get("start_transaction_generation", 0)
        if type(prior_gen) is not int or prior_gen < 0:
            return StartPendingResult(StartPendingStatus.NOT_COMMITTED, reason="prior_generation_invalid")
        generation = prior_gen + 1
    candidate_dict = dict(candidate)
    try:
        candidate_hash = hashlib.sha256(json.dumps(
            candidate_dict, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")).hexdigest()
    except (TypeError, ValueError, UnicodeError):
        return StartPendingResult(StartPendingStatus.NOT_COMMITTED,
                                  reason="candidate_not_json_serializable")
    pending_doc = {
        START_PENDING_KEY: {
            "schema_version": 1, "phase": "START_PENDING",
            "transaction_id": str(transaction_id), "generation": generation,
            "previous_exists": prior_raw is not None,
            "previous_generation": generation - 1,
            "previous_raw_utf8": prior_raw.decode("utf-8") if prior_raw is not None else "",
            "previous_sha256": hashlib.sha256(prior_raw or b"").hexdigest(),
            "candidate": candidate_dict, "candidate_sha256": candidate_hash,
        }
    }
    status, _ = compare_replace_session(path, prior_raw, pending_doc)
    observed, envelope, error = read_start_pending(path)
    classified = StartPendingStatus(status)
    if status == StartPendingStatus.COMMITTED.value:
        if error or observed is None or envelope != pending_doc[START_PENDING_KEY]:
            classified = StartPendingStatus.OUTCOME_UNCERTAIN
    elif observed is None and prior_raw is None:
        classified = StartPendingStatus.NOT_COMMITTED
    return StartPendingResult(classified,
                              observed if envelope is not None else None,
                              envelope if envelope is not None else None,
                              observed, error)


def finish_start_pending(expected_pending_raw: bytes, pending: Mapping[str, Any],
                         replacement: Mapping[str, Any] | None = None, *,
                         action: StartPendingAction = StartPendingAction.COMMIT,
                         path: str | Path = SESSION_FILE) -> StartPendingResult:
    """CAS commit candidate or restore exact prior bytes/absence."""
    current_raw, current, error = read_start_pending(path)
    if error or current is None or current_raw != expected_pending_raw:
        return StartPendingResult(StartPendingStatus.OUTCOME_UNCERTAIN, reason=error or "pending_mismatch")
    if (current.get("transaction_id") != pending.get("transaction_id")
            or current.get("generation") != pending.get("generation")):
        return StartPendingResult(StartPendingStatus.NOT_COMMITTED, reason="transaction_identity_mismatch")
    prior = pending.get("previous_raw_utf8", "").encode("utf-8")
    if action == StartPendingAction.ROLLBACK:
        if pending.get("previous_exists"):
            try:
                prior_document = json.loads(prior.decode("utf-8"))
            except (UnicodeError, ValueError):
                return StartPendingResult(StartPendingStatus.NOT_COMMITTED, reason="embedded_prior_invalid")
            status, observed = compare_replace_session(
                path, expected_pending_raw, prior_document,
                transaction_id=str(pending["transaction_id"]), generation=pending["generation"],
                replacement_bytes=prior,
            )
            if status == "COMMITTED" and observed != prior:
                status = StartPendingStatus.OUTCOME_UNCERTAIN.value
        else:
            status = compare_delete_session(
                path, expected_pending_raw,
                transaction_id=str(pending["transaction_id"]), generation=pending["generation"],
            )
            observed = None
        try:
            actual = Path(path).read_bytes()
        except FileNotFoundError:
            actual = None
        except OSError:
            actual = b"?"
        expected_after = prior if pending.get("previous_exists") else None
        if status == "COMMITTED" and actual != expected_after:
            status = StartPendingStatus.OUTCOME_UNCERTAIN.value
        return StartPendingResult(StartPendingStatus(status), observed_raw=actual)
    if action != StartPendingAction.COMMIT or replacement is None:
        return StartPendingResult(StartPendingStatus.NOT_COMMITTED, reason="commit_candidate_required")
    document = dict(replacement)
    if document != dict(pending.get("candidate", {})):
        return StartPendingResult(StartPendingStatus.NOT_COMMITTED, reason="candidate_mismatch")
    document["start_transaction_generation"] = pending["generation"]
    status, observed = compare_replace_session(
        path, expected_pending_raw, document,
        transaction_id=str(pending["transaction_id"]), generation=pending["generation"],
    )
    if status == "COMMITTED":
        try:
            readback = Path(path).read_bytes()
        except OSError:
            return StartPendingResult(StartPendingStatus.OUTCOME_UNCERTAIN, reason="candidate_readback_failed")
        if readback != observed:
            return StartPendingResult(StartPendingStatus.OUTCOME_UNCERTAIN, observed_raw=readback,
                                      reason="candidate_readback_mismatch")
        observed = readback
    return StartPendingResult(StartPendingStatus(status), observed_raw=observed)
