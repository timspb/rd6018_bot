#!/usr/bin/env python3
"""Stage and invoke the supervised D061 takeover smoke on node104.

This runner only stages an exact candidate plus the reviewed acceptance overlay;
all physical behavior runs through the typed canonical APIs on node104.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
import tarfile
import uuid

from tools import d061_transport_windows as staging

TAKEOVER_OVERLAY = staging.OVERLAY_FILES + ("takeover.py",)
SUPPLEMENTAL_FILES = ()  # The canonical 594a386 source already includes these fixes.
# Host-side fixed trust anchor; Windows cannot import Linux-only fcntl from pairing.
MANIFEST_SHA256 = "8e31b6d11c1fa2c9acbf038cd79e4f0adee7c011f8026656987c8891651ca288"
# Reviewed overlay bytes are independently pinned. The canonical manifest does
# not authorize or hash these supplemental acceptance/runtime files.
OVERLAY_SHA256 = {
    "__init__.py": "8916a792bc662348516c0693cf7a664ad846b9f4c78f09336ac0bd6e65464720",
    "guard.py": "401e16f8caff6f5d5284257dbf240b280cc384444052014b90ff5883b2b2814d",
    "adapters.py": "d0f8a85772833e81e68c2c3291415beb7b9a9c02aa0b0d849e0acec84923e66c",
    "transient.py": "99abd8ea5b97abbed02f9a3b367b55d4cb0da3044984b0fcfcc5e62a7a74abff",
    "pairing.py": "4907ad353badb1d5a35c4e9a4ab6d83c5eb9d2ce830195994f0c28fd752d2ba9",
    "takeover.py": "2a8eb1ac9062d88d62ff0d4a247c5b71af2f31fbf6c65212fb8b6b2d3dfeb889",
}
RESULT_PATH = Path(os.environ.get("RD6018_D061_RESULT", "d061-takeover-result.json"))
EVIDENCE_DIR = Path(os.environ.get("RD6018_D061_EVIDENCE_DIR", "d061-takeover-evidence"))



def _add_regular_file(archive: tarfile.TarFile, path: Path, arcname: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("required regular takeover overlay unavailable: " + arcname)
    info = archive.gettarinfo(str(path), arcname=arcname)
    with path.open("rb") as stream:
        archive.addfile(info, stream)


def make_takeover_overlay(manifest_bytes: bytes) -> bytes:
    """Stage only six byte-pinned supplemental modules for exact 594a386."""
    if hashlib.sha256(manifest_bytes).hexdigest() != MANIFEST_SHA256:
        raise RuntimeError("untrusted exact-source manifest; refusing to stage")
    supplemental = {"tools/acceptance_guard/" + name: OVERLAY_SHA256[name]
                    for name in TAKEOVER_OVERLAY}
    attestation = {"overrides": {}, "supplemental": supplemental,
                   "modes": {name: 0o644 for name in supplemental}}
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:gz") as archive:
        for name in TAKEOVER_OVERLAY:
            _add_pinned_file(archive, staging.OVERLAY / name,
                             "tools/acceptance_guard/" + name, OVERLAY_SHA256[name])
        info = tarfile.TarInfo("source-manifest.json")
        info.size, info.mode = len(manifest_bytes), 0o600
        archive.addfile(info, io.BytesIO(manifest_bytes))
        raw_attestation = json.dumps(attestation, sort_keys=True, separators=(",", ":")).encode()
        info = tarfile.TarInfo("overlay-attestation.json")
        info.size, info.mode = len(raw_attestation), 0o600
        archive.addfile(info, io.BytesIO(raw_attestation))
    return data.getvalue()


def _add_pinned_file(archive: tarfile.TarFile, path: Path, arcname: str, expected: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("required regular takeover overlay unavailable: " + arcname)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise RuntimeError("reviewed takeover overlay hash mismatch: " + arcname)
    info = archive.gettarinfo(str(path), arcname=arcname)
    info.size = len(raw)
    info.mode = 0o644
    archive.addfile(info, io.BytesIO(raw))


def validate_takeover_overlay(overlay_bytes: bytes, expected_sha256: str) -> dict[str, str]:
    """Reject unexpected paths, metadata and any non-byte-pinned module."""
    if hashlib.sha256(overlay_bytes).hexdigest() != expected_sha256:
        raise RuntimeError("overlay archive SHA256 mismatch")
    supplemental = {"tools/acceptance_guard/" + name: OVERLAY_SHA256[name]
                    for name in TAKEOVER_OVERLAY}
    expected_names = set(supplemental) | {"source-manifest.json", "overlay-attestation.json"}
    seen, contents = {}, {}
    with tarfile.open(fileobj=io.BytesIO(overlay_bytes), mode="r:gz") as archive:
        for member in archive.getmembers():
            name = member.name
            path = Path(name)
            if (path.is_absolute() or ".." in path.parts or "\\" in name
                    or not member.isfile() or name in seen or name not in expected_names):
                raise RuntimeError("invalid or duplicate overlay member: " + name)
            stream = archive.extractfile(member)
            if stream is None:
                raise RuntimeError("unreadable overlay member: " + name)
            raw = stream.read()
            seen[name] = hashlib.sha256(raw).hexdigest()
            contents[name] = raw
            expected_mode = 0o600 if name.endswith(".json") else 0o644
            if stat.S_IMODE(member.mode) != expected_mode:
                raise RuntimeError("overlay file mode mismatch: " + name)
    if set(seen) != expected_names or seen.get("source-manifest.json") != MANIFEST_SHA256:
        raise RuntimeError("overlay archive paths or exact-source manifest mismatch")
    try:
        attestation = json.loads(contents["overlay-attestation.json"])
    except (ValueError, TypeError, KeyError) as exc:
        raise RuntimeError("invalid overlay attestation") from exc
    if attestation != {"overrides": {}, "supplemental": supplemental,
                       "modes": {name: 0o644 for name in supplemental}}:
        raise RuntimeError("overlay attestation path set mismatch")
    for name, digest in supplemental.items():
        if seen.get(name) != digest:
            raise RuntimeError("attested supplemental hash mismatch: " + name)
    return seen


def read_pinned_manifest(path: Path) -> bytes:
    """Load an existing authoritative manifest; never synthesize one."""
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("authoritative exact-source manifest unavailable")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise RuntimeError("untrusted exact-source manifest; refusing to stage")
    return raw


def normalize_git_archive(archive_bytes: bytes, manifest_bytes: bytes) -> bytes:
    """Return a tar whose regular files are exactly the pinned Git blobs.

    Windows git archive applies autocrlf on checkout. Only CRLF-to-LF bytes
    that independently reach the pinned digest are normalized.
    """
    if hashlib.sha256(manifest_bytes).hexdigest() != MANIFEST_SHA256:
        raise RuntimeError("untrusted exact-source manifest")
    import json
    expected = json.loads(manifest_bytes)
    if len(expected) != 875 or not isinstance(expected, dict):
        raise RuntimeError("exact-source manifest must contain 875 files")
    source = {}
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
        for member in archive.getmembers():
            name = member.name
            path = Path(name)
            if (path.is_absolute() or ".." in path.parts or "\\" in name
                    or not name or name.startswith("./")):
                raise RuntimeError("invalid archive member: " + name)
            if member.isdir():
                continue
            if not member.isfile() or name in source:
                raise RuntimeError("invalid archive member: " + name)
            stream = archive.extractfile(member)
            if stream is None:
                raise RuntimeError("archive member unreadable: " + name)
            source[name] = (stream.read(), member.mode)
    if set(source) != set(expected):
        raise RuntimeError("archive paths differ from exact-source manifest")
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:") as archive:
        for name, digest in expected.items():
            raw, file_mode = source[name]
            if hashlib.sha256(raw).hexdigest() != digest:
                normalized = raw.replace(b"\r\n", b"\n")
                if hashlib.sha256(normalized).hexdigest() != digest:
                    raise RuntimeError("canonical archive hash mismatch: " + name)
                raw = normalized
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            info.mode = file_mode & 0o777
            archive.addfile(info, io.BytesIO(raw))
    return output.getvalue()


FAULT_OPERATION = "d061_fault_raw_protection_unavailable"


def remote_takeover_command(stage: str, fault_operation: str | None = None) -> str:
    """Launch the reviewed transaction through an isolated node104 Python."""
    # The remote entry module owns the canonical API wiring; Telegram dispatch
    # is suppressed by acceptance_guard.pairing and only typed socket ops mutate.
    if fault_operation not in (None, FAULT_OPERATION):
        raise ValueError("unsupported D061 fault operation")
    fault_arg = "" if fault_operation is None else ", fault_operation=" + repr(fault_operation)
    code = (
        "import asyncio, os, sys; "
        "from pathlib import Path; "
        "sys.path.insert(0, " + repr(stage) + "); "
        "from tools.acceptance_guard.takeover import run_node104; "
        "asyncio.run(run_node104(Path(" + repr(stage) + ")" + fault_arg + "))"
    )
    return "sudo -n sh -c " + shlex.quote(
        "set -a; . " + shlex.quote(staging.PRODUCTION_ENV) + "; set +a; "
        "cd " + shlex.quote(stage) + "/state; "
        "RD6018_PHYSICAL_TEST_CONTROL=1 PYTHONPATH=" + shlex.quote(stage) + " "
        + shlex.quote(staging.PYTHON) + " -B -c " + shlex.quote(code)
    )


def stage_candidate(client, archive_bytes: bytes, overlay_bytes: bytes) -> tuple[str, str, str]:
    """Create a unique mode-700 stage and unpack candidate and overlay."""
    tx = uuid.uuid4().hex
    stage = staging.STAGE_ROOT + "/rd6018-d061-takeover-" + tx
    archive_remote = stage + ".tar"
    overlay_remote = stage + "-overlay.tar.gz"
    sftp = client.open_sftp()
    try:
        for remote, payload in ((archive_remote, archive_bytes), (overlay_remote, overlay_bytes)):
            with sftp.file(remote, "wb") as stream:
                stream.write(payload)
    finally:
        sftp.close()
    overlay_sha = hashlib.sha256(overlay_bytes).hexdigest()
    validate_takeover_overlay(overlay_bytes, overlay_sha)
    prep = ("set -eu; echo 'D061 overlay archive expected sha256=" + overlay_sha + "'; "
            + "actual=$(sha256sum " + shlex.quote(overlay_remote) + " | cut -d' ' -f1); "
            + "echo 'D061 overlay archive actual sha256='\"$actual\"; test \"$actual\" = "
            + shlex.quote(overlay_sha) + "; test ! -e " + shlex.quote(stage) + "; mkdir -m 700 "
            + shlex.quote(stage) + "; mkdir -m 700 " + shlex.quote(stage + "/.canonical-source")
            + "; tar -xf " + shlex.quote(archive_remote)
            + " -C " + shlex.quote(stage + "/.canonical-source")
            + "; cp -a " + shlex.quote(stage + "/.canonical-source/.") + " " + shlex.quote(stage)
            + "; tar -xzf " + shlex.quote(overlay_remote)
            + " -C " + shlex.quote(stage) + "; mkdir -m 700 "
            + shlex.quote(stage + "/state"))
    staging.remote_exec(client, prep)
    return stage, archive_remote, overlay_remote


def read_root_owned_transaction(client, stage: str) -> dict:
    """Read the mode-0600 node104 receipt without weakening its permissions.

    SFTP runs as the unprivileged operator and cannot open root-owned state;
    keep its evidence root-only and use the already pinned SSH sudo boundary.
    """
    prefix = staging.STAGE_ROOT + "/rd6018-d061-takeover-"
    if not stage.startswith(prefix) or not stage[len(prefix):].isalnum():
        raise RuntimeError("untrusted D061 evidence stage path")
    command = "sudo -n cat -- " + shlex.quote(stage + "/state/d061-takeover-result.json")
    receipt = json.loads(staging.remote_exec(client, command, timeout=30))
    if not isinstance(receipt, dict) or receipt.get("result") not in ("PASS", "FAIL"):
        raise RuntimeError("invalid root-owned D061 receipt")
    return receipt


def cleanup_remote_staging(client, stage, archives, *, completed):
    """Delete remote staging only after a positively completed transaction."""
    if stage and completed:
        try:
            staging.remote_exec(client, "sudo -n rm -rf -- " + shlex.quote(stage))
        except Exception:
            print("Successful takeover stage could not be removed; retained at " + stage, file=sys.stderr)
    for remote in archives:
        if remote and completed:
            try:
                staging.remote_exec(client, "rm -f -- " + shlex.quote(remote))
            except Exception:
                print("Successful takeover archive could not be removed; retained at " + remote, file=sys.stderr)
    if stage and not completed:
        print("Takeover failed; staged recovery evidence retained at " + stage, file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physical-ready", action="store_true", help="physical preflight, cutoff, sensor, supervision and exact firmware are confirmed")
    parser.add_argument("--fault-operation", choices=(FAULT_OPERATION,), default=None,
                        help="explicitly inject synthetic raw-protection evidence loss after D061 proof")
    args = parser.parse_args()
    if not args.physical_ready:
        parser.error("--physical-ready is required for this supervised physical smoke")
    client = None
    stage = archive_remote = overlay_remote = None
    completed = False
    evidence = {
        "operation": ("D061 positive takeover only" if args.fault_operation is None
                      else "D061 INJECTED RAW PROTECTION EVIDENCE LOSS"),
        "fault_operation": args.fault_operation,
        "node": "node104",
        "candidate_sha": staging.SHA,
        "manifest_sha256": MANIFEST_SHA256,
        "result": "BLOCKED",
    }
    try:
        if os.name != "nt":
            raise RuntimeError("this runner must be executed with Windows Python")
        if not staging.CANDIDATE.is_dir() or staging.CANDIDATE.is_symlink():
            raise RuntimeError("exact candidate directory is unavailable")
        if staging.git("rev-parse", "HEAD", cwd=staging.CANDIDATE) != staging.SHA or staging.git(
                "status", "--porcelain", "--untracked-files=all", cwd=staging.CANDIDATE):
            raise RuntimeError("candidate must be clean and at the exact required SHA")
        raw_archive = subprocess.check_output(["git", "archive", "--format=tar", staging.SHA],
                                                cwd=staging.CANDIDATE)
        manifest_path = staging.CANDIDATE / "source-manifest.json"
        # A manifest may be supplied beside the exact candidate by the acceptance
        # fixture; it is never generated from a working tree or supplemental files.
        if not manifest_path.is_file():
            manifest_path = staging.OVERLAY / "source-manifest.json"
        manifest_bytes = read_pinned_manifest(manifest_path)
        archive_bytes = normalize_git_archive(raw_archive, manifest_bytes)
        overlay_bytes = make_takeover_overlay(manifest_bytes)
        profile = staging.profile_values()
        client = staging.connect(profile)
        before = staging.service_state(client)
        evidence["production_service_before"] = before
        if before.get("ActiveState") != "active" or before.get("MainPID", "0") == "0":
            raise RuntimeError("production service must be active before takeover handover")
        stage, archive_remote, overlay_remote = stage_candidate(client, archive_bytes, overlay_bytes)
        evidence["stage_path"] = stage
        evidence["overlay_archive_sha256"] = hashlib.sha256(overlay_bytes).hexdigest()
        print(staging.remote_exec(client, remote_takeover_command(stage, args.fault_operation), timeout=900))
        evidence["transaction"] = read_root_owned_transaction(client, stage)
        after = staging.service_state(client)
        evidence["production_service_after"] = after
        if (after.get("ActiveState") != "active" or after.get("MainPID", "0") == "0"
                or after.get("NRestarts") != before.get("NRestarts")):
            raise RuntimeError("production restore/service restart-count proof failed")
        if evidence["transaction"].get("result") != "PASS":
            raise RuntimeError("remote takeover evidence did not report PASS")
        completed = True
        evidence["result"] = "PASS"
        return 0
    except Exception as exc:
        evidence["error"] = str(exc)
        print(str(exc), file=sys.stderr)
        remote_output = getattr(exc, "output", "")
        if remote_output:
            evidence["remote_output"] = remote_output[-12000:]
            for line in remote_output.splitlines():
                try:
                    candidate = json.loads(line)
                except (TypeError, ValueError):
                    continue
                if isinstance(candidate, dict) and candidate.get("result") in ("PASS", "FAIL"):
                    evidence["transaction"] = candidate
                    break
            print(remote_output, file=sys.stderr)
        return 1
    finally:
        if client is not None:
            cleanup_remote_staging(client, stage, (archive_remote, overlay_remote),
                                   completed=completed)
            client.close()
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        stamp = __import__("datetime").datetime.now().strftime("%Y%m%d-%H%M%S")
        prefix = "d061-positive-" if args.fault_operation is None else "d061-fault-raw-protection-"
        evidence_file = EVIDENCE_DIR / (prefix + stamp + ".json")
        evidence_file.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                                 encoding="utf-8")
        RESULT_PATH.write_text(
            str(evidence.get("operation")) + " result: " + str(evidence.get("result")) + "\n"
            + "Evidence: " + str(evidence_file) + "\n"
            + json.dumps({key: evidence.get(key) for key in
                          ("candidate_sha", "manifest_sha256", "overlay_archive_sha256",
                           "production_service_before", "production_service_after")},
                         indent=2, sort_keys=True) + "\n",
            encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
