"""D125 read-only persisted-session classifier for D090 release planning.

Never converts an active session into OFF/retired; never writes to the file.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

class SessionEvidenceError(RuntimeError):
    pass

def inspect_session(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise SessionEvidenceError("session absent, linked, or not regular")
    raw=path.read_bytes()
    try:
        data=json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise SessionEvidenceError("session JSON invalid") from exc
    if type(data) is not dict:
        raise SessionEvidenceError("session schema invalid")
    sid=data.get("v2_trace_session_id")
    battery=data.get("v2_battery_id")
    stage=data.get("stage")
    retired=(data.get("owner")=="runtime.charge.persistence" and
        data.get("schema_version")==1 and data.get("state")=="retired" and
        data.get("stage")=="RETIRED" and
        data.get("retirement_kind")=="operator_recovery_clearance" and
        data.get("output_intent")=="verified_off")
    if retired:
        classification="retired"
    elif isinstance(sid,str) and sid and isinstance(stage,str) and stage:
        classification="preserved_nonterminal"
    else:
        classification="unknown_blocked"
    return {"classification":classification,"session_sha256":hashlib.sha256(raw).hexdigest(),
        "session_id":sid if isinstance(sid,str) else None,
        "battery_id":battery if isinstance(battery,str) else None,
        "stage":stage if isinstance(stage,str) else None,
        "mutation_authorized":False,
        "safe_to_auto_resume":False if classification!="retired" else None}
