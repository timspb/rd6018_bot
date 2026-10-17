#!/usr/bin/env python3
"""D090 exact-release preparation and fail-closed node104 transaction gates.

This module is intentionally offline.  It never opens SSH, calls systemd, or
connects to HA/ESPHome.  A future node-local executor must consume these typed
proofs and the pinned transaction manifest before it can mutate a host.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import tempfile
import time
from typing import Any

SOURCE_SHA = "d29db790bf7140932bc005bddf6bd5988041bfc0"
OLD_SHA = "8b75cca153f00847d84396aba392472bb7552ad4"
STAGING_MANIFEST_SHA256 = "e3fb80039974a72bc0366bab8e21938d7963632610289d67c20f26dfa7fd4b80"
STAGING_ARCHIVE_SHA256 = "3066e46ccb34b9f1f9712282ff32e15d2c5f6444b8886a481bd5d7c9a3c9ba2d"
NODE = "node104"
HOSTNAME = "rd6018-bot"
MACHINE_ID = "d2a570f751e14d8cbc654b5c4559ce24"
SERVICE = "rd6018-bot.service"
ROOT = "/opt/services/rd6018-bot"
FIRMWARE = "2.2-autonomous-authority"
EDGE_LEASE_TTL_S = 900
EDGE_RENEWAL_S = 300
EVIDENCE_MAX_AGE_S = 30
REQUIRED_BENCH_CASES = (
    "D061", "D062", "D063", "D064_thermal", "D064_raw_protection",
    "D065_enter_exit", "D065_outage", "D065_managed_expiry",
    "D065_autonomous_reboot", "D065_managed_reboot", "D065_conflict",
    "D065_limits", "source_heartbeat",
)
# Set only after reviewing and accepting an out-of-band physical-evidence
# signing key. D090 intentionally has no trusted physical record signer yet.
PHYSICAL_SIGNER_KEY_SHA256: str | None = None


@dataclass(frozen=True)
class ReleaseManifest:
    schema: int
    node: str
    hostname: str
    machine_id: str
    service: str
    root: str
    old_source_sha: str
    source_sha: str
    source_archive_sha256: str
    staging_manifest_sha256: str
    python: str
    firmware: str
    firmware_digest: str | None
    systemd_unit_sha256: str
    service_environment_sha256: str
    external_voltage_observer: str
    edge_lease_ttl_s: int
    edge_renewal_s: int
    expected_state: str
    expected_session: str
    expected_quarantine: str
    physical_acceptance: str


PINNED = ReleaseManifest(
    schema=1, node=NODE, hostname=HOSTNAME, machine_id=MACHINE_ID,
    service=SERVICE, root=ROOT, old_source_sha=OLD_SHA,
    source_sha=SOURCE_SHA,
    # The stage manifest/marker from the supplied D089 staging evidence is the
    # local trust root. Archive hash is verified from the immutable manifest.
    source_archive_sha256=STAGING_ARCHIVE_SHA256,
    staging_manifest_sha256=STAGING_MANIFEST_SHA256,
    python="3.11", firmware=FIRMWARE, firmware_digest=None,
    systemd_unit_sha256="74146a925d8c80a6a240f78877e76e060e674f6928f748db43891e7ff1b0e068",
    service_environment_sha256="3ca2c77f25c0cde39d5c405114220dc6135197e1f68f3371e9ba8b7ff473a185",
    external_voltage_observer="HA102 + native ESP128 SensorState; independent processes",
    edge_lease_ttl_s=EDGE_LEASE_TTL_S, edge_renewal_s=EDGE_RENEWAL_S,
    expected_state="capture exact live state inventory; preserve byte-for-byte",
    expected_session="absent at D089 observation; recheck stopped and preserve",
    expected_quarantine="absent at D089 observation; recheck stopped and preserve",
    physical_acceptance="OPEN: exact Python/firmware D061-D065 contract",
)


class GateError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_member(name: str) -> None:
    p = PurePosixPath(name)
    if not name or p.is_absolute() or ".." in p.parts or "\\" in name:
        raise GateError(f"unsafe release path: {name!r}")


def verify_staged_release(release: Path) -> dict[str, Any]:
    """Verify the exact staged source before any host-specific operation."""
    manifest_path = release / "RELEASE_MANIFEST.json"
    marker_path = release / "STAGED_OK"
    archive = release / "source.tar"
    if any(p.is_symlink() for p in (release, manifest_path, marker_path, archive)):
        raise GateError("staging inputs must be ordinary files/directories")
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"staging metadata invalid: {exc}") from exc
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    if manifest_hash != PINNED.staging_manifest_sha256:
        raise GateError("staged manifest digest differs from D090 pin")
    if marker.get("manifest_sha256") != manifest_hash or marker.get("tree_verified") is not True:
        raise GateError("staging completion marker does not bind the manifest")
    if manifest.get("source_sha") != PINNED.source_sha or manifest.get("node") != NODE or manifest.get("service") != "rd6018-bot":
        raise GateError("staged release identity/SHA mismatch")
    if sha256_file(archive) != manifest.get("archive_sha256"):
        raise GateError("source archive digest differs from manifest")
    if sha256_file(archive) != PINNED.source_archive_sha256:
        raise GateError("source archive digest differs from D090 pin")
    declared: set[str] = set()
    with tarfile.open(archive, "r:") as bundle:
        for member in bundle.getmembers():
            _safe_member(member.name)
            if member.isdir():
                continue
            if not member.isfile():
                raise GateError(f"unsupported archive member type: {member.name}")
            if member.name in declared:
                raise GateError(f"duplicate archive path: {member.name}")
            declared.add(member.name)
            entry = next((x for x in manifest.get("files", []) if x.get("path") == member.name), None)
            if entry is None or entry.get("size") != member.size:
                raise GateError(f"manifest file/size mismatch: {member.name}")
            f = bundle.extractfile(member)
            if f is None or hashlib.sha256(f.read()).hexdigest() != entry.get("sha256"):
                raise GateError(f"manifest content mismatch: {member.name}")
    if len(declared) != len(manifest.get("files", [])):
        raise GateError("manifest/archive file set differs")
    tree = release / "tree"
    for path in tree.rglob("*"):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise GateError(f"staged tree contains unsupported filesystem object: {path.relative_to(tree)}")
    actual_tree = {p.relative_to(tree).as_posix() for p in tree.rglob("*") if p.is_file()}
    if actual_tree != declared:
        raise GateError("staged extracted tree file set differs")
    for entry in manifest["files"]:
        path = tree / entry["path"]
        if path.is_symlink() or not path.is_file() or path.stat().st_size != entry["size"] or sha256_file(path) != entry["sha256"]:
            raise GateError(f"staged extracted file mismatch: {entry['path']}")
    return manifest


def _num(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


@dataclass(frozen=True)
class PhysicalOffProof:
    captured_at_epoch: float
    host_machine_id: str
    service_main_pid: int
    ha102_output_off: bool | None
    ha102_voltage_v: float | None
    ha102_current_a: float | None
    esp128_output_off: bool
    esp128_voltage_v: float
    esp128_current_a: float
    native_sensor_state_fresh: bool
    edge_lease_armed: bool
    edge_boot_quarantine: bool
    physical_node_owner_count: int
    active_session: bool
    source_nonces: tuple[str, str]


def validate_physical_off(proof: PhysicalOffProof, *, now: float | None = None,
                          require_service_stopped: bool = True) -> None:
    """Validate post-stop ESP Native API proof; HA is optional cached advisory."""
    now = time.time() if now is None else now
    if not isinstance(proof, PhysicalOffProof):
        raise GateError("unknown physical proof type")
    if type(proof.host_machine_id) is not str or proof.host_machine_id != MACHINE_ID:
        raise GateError("physical proof belongs to another host")
    if not _num(proof.captured_at_epoch) or not 0 <= now - proof.captured_at_epoch <= EVIDENCE_MAX_AGE_S:
        raise GateError("physical OFF proof is expired, future dated, or invalid")
    if type(proof.service_main_pid) is not int or proof.service_main_pid < 0:
        raise GateError("service MainPID must be a nonnegative integer")
    if require_service_stopped and proof.service_main_pid != 0:
        raise GateError("service is not confirmed stopped")
    if any(type(value) is not bool for value in (proof.esp128_output_off,
            proof.native_sensor_state_fresh, proof.edge_lease_armed,
            proof.edge_boot_quarantine, proof.active_session)):
        raise GateError("native physical proof flags must be booleans")
    if not proof.esp128_output_off or not proof.native_sensor_state_fresh:
        raise GateError("fresh authoritative Native ESP Output OFF proof required")
    if (type(proof.source_nonces) is not tuple or len(proof.source_nonces) != 2
            or any(type(value) is not str or not value for value in proof.source_nonces)
            or len(set(proof.source_nonces)) != 2):
        raise GateError("distinct capture-path identifiers missing/reused")
    # Both API paths terminate in the SAME ESP. HA is diagnostic only:
    # missing, stale, contradictory or malformed HA data cannot modify
    # Native API physical admission. These legacy HA fields are not used
    # for any D090 safety decision or immutable baseline fingerprint.
    for value in (proof.esp128_voltage_v, proof.esp128_current_a):
        if not _num(value) or abs(value) > .05:
            raise GateError("authoritative native output voltage/current must be zero")
    if proof.edge_lease_armed or proof.edge_boot_quarantine:
        raise GateError("edge lease must be disarmed and boot quarantine clear")
    if type(proof.physical_node_owner_count) is not int or proof.physical_node_owner_count != 1 or proof.active_session:
        raise GateError("exactly one independent physical node owner and no active persisted session required")


def validate_physical_acceptance(record: dict[str, Any], evidence_dir: Path) -> None:
    """Require exact source+firmware compiled/flashed physical case artifacts."""
    if record.get("source_sha") != SOURCE_SHA or record.get("firmware") != FIRMWARE:
        raise GateError("exact Python/ESPHome pairing acceptance is missing")
    firmware_digest = record.get("firmware_sha256")
    if not isinstance(firmware_digest, str) or len(firmware_digest) != 64:
        raise GateError("firmware binary digest is not pinned by acceptance evidence")
    if PINNED.firmware_digest is None or firmware_digest != PINNED.firmware_digest:
        raise GateError("firmware digest has no reviewed D090 trust pin")
    signer_hash = record.get("signer_key_sha256")
    signature_name = record.get("signature_file")
    signature_hash = record.get("signature_sha256")
    key_name = record.get("signer_public_key_file")
    if (PHYSICAL_SIGNER_KEY_SHA256 is None or signer_hash != PHYSICAL_SIGNER_KEY_SHA256
            or not isinstance(signature_name, str) or Path(signature_name).name != signature_name
            or not isinstance(key_name, str) or Path(key_name).name != key_name
            or not isinstance(signature_hash, str) or len(signature_hash) != 64):
        raise GateError("signed physical acceptance lacks a reviewed signer trust pin")
    signature = evidence_dir / signature_name
    key = evidence_dir / key_name
    if (signature.is_symlink() or key.is_symlink() or not signature.is_file() or not key.is_file()
            or sha256_file(signature) != signature_hash or sha256_file(key) != signer_hash):
        raise GateError("physical acceptance signature/key digest mismatch")
    signed_payload = {key: value for key, value in record.items()
                      if key not in {"signature_file", "signature_sha256", "signer_public_key_file"}}
    with tempfile.TemporaryDirectory(prefix="d090-acceptance-") as temp:
        payload = Path(temp) / "acceptance.json"
        payload.write_text(json.dumps(signed_payload, sort_keys=True, separators=(",", ":")) + "\n",
                           encoding="utf-8")
        try:
            subprocess.run(["openssl", "dgst", "-sha256", "-verify", str(key),
                            "-signature", str(signature), str(payload)],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=10)
        except (OSError, subprocess.SubprocessError) as exc:
            raise GateError("physical acceptance signature verification failed") from exc
    if record.get("compiled_flashed_bench_validated") is not True:
        raise GateError("exact firmware must be compiled, flashed, and bench validated")
    cases = record.get("cases")
    if not isinstance(cases, dict):
        raise GateError("physical case evidence is absent")
    for case in REQUIRED_BENCH_CASES:
        item = cases.get(case, {})
        name = item.get("file") if isinstance(item, dict) else None
        if not isinstance(name, str) or Path(name).name != name:
            raise GateError(f"unsafe or missing physical acceptance artifact: {case}")
        path = evidence_dir / name
        if path.is_symlink() or not path.is_file() or item.get("status") != "PASS" or sha256_file(path) != item.get("sha256"):
            raise GateError(f"physical acceptance OPEN: {case}")


def preflight_report(release: Path) -> dict[str, Any]:
    manifest = verify_staged_release(release)
    return {
        "decision": "PREPARE_ONLY_PASS",
        "source_sha": manifest["source_sha"],
        "manifest_sha256": PINNED.staging_manifest_sha256,
        "source_files": len(manifest["files"]),
        "activation_authorized": False,
        "blockers": [
            "no D090 exact-source fresh physical OFF proof supplied",
            "exact D061-D065 Python/ESPHome 2.2 physical acceptance remains OPEN",
            "installed 8b75cca source bytes must be captured and hashed from host; Git object is absent locally",
        ],
    }
