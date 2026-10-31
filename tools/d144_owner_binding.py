"""Read-only production admission through the canonical D090 transaction owner.

D144's engine remains deliberately disconnected from production service lifecycle.
This operation acquires the SAME lock that owns D090, runs the reviewed D142
combined proof, and returns evidence, never authorization to start a cutover.
"""
from __future__ import annotations

from pathlib import Path

import node104_d090_transaction as d090
from tools.d142_readonly_prestop import assess


def prepare_only(owner: d090.D090Transaction, *, stage: Path,
                 source_sha: str, preimage_sha256: str,
                 collector: Path) -> dict:
    if (owner.offline or owner.root != Path(d090.release.ROOT)
            or owner.host_check is not d090.production_host_check
            or not owner.software_release
            or not isinstance(owner.service, d090.SystemdService)):
        raise d090.TransactionError("D144 production owner binding invalid")
    if source_sha != owner.pinned.source_sha:
        raise d090.TransactionError("D144 candidate source differs from owner pin")
    with owner._locked():
        owner.host_check()
        owner.release_admission()
        if not owner.service.layout_valid() or not owner.service.active():
            raise d090.TransactionError("D144 production layout or service is not healthy")
        pid = owner.service.main_pid()
        if pid <= 0:
            raise d090.TransactionError("D144 invalid service MainPID")
        result = assess(owner.root, stage, pid=pid, source_sha=source_sha,
                        preimage_sha256=preimage_sha256, collector=collector)
        if result.get("preflight") != "PASS_AT_OBSERVATION_ONLY":
            raise d090.TransactionError("D142 pre-stop checks did not pass")
        return {
            "schema": "D144_OWNER_PREPARE_ONLY_V1",
            "status": "PREPARE_ONLY_PASS",
            "service_pid": pid,
            "candidate_identity_sha256": result["candidate_identity_sha256"],
            "observed_preimage_sha256": preimage_sha256,
            "fresh_d091_off": result["fresh_d091_off"],
            "capacity_pass": result["capacity_pass"],
            "activation_authorized": False,
        }
