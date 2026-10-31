"""D142 read-only combined pre-stop assessment, never an activation command.

Order: verify D137 live preimage + D138 staged app/venv, verify D140
capacity, THEN collect fresh independent D091 OFF evidence and validate
it with the canonical release validator. Fresh proof must never be cached
or reused for a future stop.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time

try:
    from tools.d138_candidate_preflight import inspect_candidate
    from tools.d140_disk_guard import require_capacity
except ModuleNotFoundError:
    from d138_candidate_preflight import inspect_candidate
    from d140_disk_guard import require_capacity

import node104_d090_release as release


def validate_snapshot(raw: dict, *, pid: int, now: float) -> None:
    required = set(release.PhysicalOffProof.__dataclass_fields__)
    if type(raw) is not dict or set(raw) != required:
        raise ValueError("D091 proof schema mismatch")
    if type(raw.get("source_nonces")) is not list:
        raise ValueError("D091 nonces missing")
    data = dict(raw)
    data["source_nonces"] = tuple(raw["source_nonces"])
    proof = release.PhysicalOffProof(**data)
    release.validate_physical_off(proof, require_service_stopped=False, now=now)
    if proof.service_main_pid != pid:
        raise ValueError("D091 proof belongs to another process")


def assess(root: Path, stage: Path, *, pid: int, source_sha: str,
           preimage_sha256: str, collector: Path,
           collect=None, clock=None) -> dict:
    clock = clock or time.time
    candidate = inspect_candidate(root=root, stage=stage, pid=pid,
                                  source_sha=source_sha,
                                  preimage_sha256=preimage_sha256)
    capacity = require_capacity(root, stage)
    if collect is None:
        if collector.is_symlink() or not collector.is_file():
            raise ValueError("D091 read-only collector unavailable")
        def collect():
            env = dict(os.environ)
            env["D090_EXPECTED_ESP_VERSION"] = "2.3-ha-canonical"
            env["D090_SOFTWARE_RELEASE"] = "1"
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            result = subprocess.run(
                [str(root / "venv/bin/python"), str(collector)],
                capture_output=True, text=True, timeout=50, check=False, env=env)
            if result.returncode:
                raise ValueError("fresh D091 observation failed")
            return json.loads(result.stdout)
    raw = collect()
    validate_snapshot(raw, pid=pid, now=clock())
    argv = (Path("/proc") / str(pid) / "cmdline").read_bytes().split(bytes([0]))
    if str(root / "app/bot.py").encode() not in argv:
        raise ValueError("installed service process changed during OFF observation")
    return {
        "schema": "D142_READONLY_PRESTOP_V1",
        "preflight": "PASS_AT_OBSERVATION_ONLY",
        "activation_authorized": False,
        "source_sha": source_sha,
        "candidate_identity_sha256": candidate["candidate_identity_sha256"],
        "observed_preimage_sha256": preimage_sha256,
        "capacity_pass": bool(capacity["capacity_pass"]),
        "free_bytes": capacity["observed_free_bytes"],
        "required_bytes": capacity["minimum_free_bytes"],
        "fresh_d091_off": True,
        "service_pid": pid,
        "proof_captured_at_epoch": raw["captured_at_epoch"],
        "warning": "Transient proof is not a reusable cutover token; reobserve immediately before production stop.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/opt/services/rd6018-bot"))
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--preimage-sha256", required=True)
    parser.add_argument("--collector", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(assess(args.root, args.stage, pid=args.pid, source_sha=args.source_sha,
                            preimage_sha256=args.preimage_sha256, collector=args.collector),
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
