#!/usr/bin/env python3
"""Fail-closed node104 preparation and local transaction simulator.

No production activation, SSH, systemctl, OTA, lease, or actuator operation is
implemented. ``stage`` creates an exact-SHA release; ``preflight`` validates
fresh independent evidence; ``simulate_transaction`` exercises the ordinary
directory swap and crash recovery below a caller-owned temporary root.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import re
from pathlib import Path, PurePosixPath

if os.name == "nt":
    import msvcrt
else:
    import fcntl

EXPECTED_NODE = "node104"
EXPECTED_SERVICE = "rd6018-bot"
EXPECTED_EXEC_START = "/opt/services/rd6018-bot/venv/bin/python /opt/services/rd6018-bot/app/bot.py"
EXPECTED_PROTECT_SYSTEM = "strict"
EXPECTED_INSTALLED_FIRMWARE = "2.0-edge-adoption"
EXPECTED_CANDIDATE_FIRMWARE = "2.2-autonomous-authority"
MANIFEST_NAME = "RELEASE_MANIFEST.json"
STAGED_MARKER = "STAGED_OK"
JOURNAL_NAME = "DEPLOYMENT_JOURNAL.json"
LOCK_NAME = "DEPLOYMENT.lock"
SIMULATION_MARKER = ".NODE104_SIMULATION_ROOT"
MAX_PREFLIGHT_AGE_SECONDS = 300


def run(*args: str) -> str:
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_relative(name: str) -> Path:
    posix = PurePosixPath(name)
    if not name or posix.is_absolute() or ".." in posix.parts or "\\" in name:
        raise RuntimeError(f"unsafe archive path: {name!r}")
    return Path(*posix.parts)


def _safe_component(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or not re.fullmatch(r"[A-Za-z0-9._-]+", value) or value in {".", ".."}:
        raise RuntimeError(f"unsafe {label}")
    return value


def source_manifest(repo: Path, revision: str) -> dict:
    actual = run("git", "-C", str(repo), "rev-parse", "--verify", f"{revision}^{{commit}}")
    if len(revision) == 40 and actual != revision:
        raise RuntimeError(f"source SHA mismatch: expected {revision}, got {actual}")
    with tempfile.TemporaryDirectory(prefix="node104-archive-") as temp:
        archive = Path(temp) / "source.tar"
        with archive.open("wb") as stream:
            subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", actual], check=True, stdout=stream)
        files = []
        with tarfile.open(archive) as bundle:
            for member in sorted(bundle.getmembers(), key=lambda item: item.name):
                if not member.isfile():
                    continue
                _safe_relative(member.name)
                extracted = bundle.extractfile(member)
                if extracted is None:
                    raise RuntimeError(f"cannot read archive member: {member.name}")
                content = extracted.read()
                files.append({"path": member.name, "mode": member.mode & 0o777, "sha256": hashlib.sha256(content).hexdigest(), "size": member.size})
        archive_sha = sha256(archive)
    return {"schema": 3, "node": EXPECTED_NODE, "service": EXPECTED_SERVICE, "source_sha": actual, "archive_sha256": archive_sha, "files": files}


def _reject_symlink(path: Path) -> None:
    if path.is_symlink():
        raise RuntimeError(f"symlink path is not accepted: {path}")


def verify_manifest(root: Path, manifest: dict) -> None:
    if manifest.get("node") != EXPECTED_NODE or manifest.get("service") != EXPECTED_SERVICE:
        raise RuntimeError("manifest scope is not node104/rd6018-bot")
    declared = set()
    for item in manifest.get("files", []):
        rel = _safe_relative(item.get("path", ""))
        key = rel.as_posix()
        if key in declared:
            raise RuntimeError(f"duplicate manifest path: {rel}")
        declared.add(key)
        path = root / rel
        _reject_symlink(path)
        if (not path.is_file()
                or path.stat().st_size != item["size"]
                or path.stat().st_mode & 0o777 != item["mode"]
                or sha256(path) != item["sha256"]):
            raise RuntimeError(f"manifest mismatch: {rel}")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and not p.is_symlink()}
    if actual != declared:
        raise RuntimeError(f"manifest file set mismatch: unexpected={sorted(actual - declared)} missing={sorted(declared - actual)}")


def _fsync_file(path: Path) -> None:
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_tree(root: Path) -> None:
    """Durably flush every regular file and directory in a copied tree."""
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError(f"cannot fsync unsafe tree: {root}")
    for path in sorted(root.rglob("*"), key=lambda item: (item.is_file(), len(item.parts))):
        if path.is_symlink():
            raise RuntimeError(f"symlink in durable tree: {path}")
        if path.is_file():
            _fsync_file(path)
    for path in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda item: len(item.parts), reverse=True):
        _fsync_directory(path)
    _fsync_directory(root)


def _write_json(path: Path, value: dict, *, replace: bool = False) -> None:
    data = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    if not replace:
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        return
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def require_staging_directory(path: Path) -> None:
    if path.exists() and path.is_symlink():
        raise RuntimeError("staging directory must not be a symlink")
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir() or path.stat().st_dev != path.parent.stat().st_dev:
        raise RuntimeError("staging must be a real directory on one filesystem")


def _extract_safe(bundle_path: Path, tree: Path) -> None:
    with tarfile.open(bundle_path) as bundle:
        for member in bundle.getmembers():
            rel = _safe_relative(member.name)
            destination = tree / rel
            if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                raise RuntimeError(f"archive member type is not allowed: {member.name}")
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=False)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() or destination.is_symlink():
                raise RuntimeError(f"archive member collision: {member.name}")
            source = bundle.extractfile(member)
            if source is None:
                raise RuntimeError(f"cannot extract archive member: {member.name}")
            with destination.open("xb") as output:
                shutil.copyfileobj(source, output)
                output.flush()
                os.fsync(output.fileno())
            os.chmod(destination, member.mode & 0o777)


def stage(repo: Path, revision: str, staging: Path) -> Path:
    manifest = source_manifest(repo, revision)
    require_staging_directory(staging)
    release = Path(tempfile.mkdtemp(prefix=f"release-{manifest['source_sha']}-", dir=staging))
    archive_path = release / "source.tar"
    with archive_path.open("xb") as stream:
        subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", manifest["source_sha"]], check=True, stdout=stream)
        stream.flush()
        os.fsync(stream.fileno())
    if sha256(archive_path) != manifest["archive_sha256"]:
        raise RuntimeError("archive digest changed during staging")
    tree = release / "tree"
    tree.mkdir()
    _extract_safe(archive_path, tree)
    verify_manifest(tree, manifest)
    _write_json(release / MANIFEST_NAME, manifest)
    _write_json(release / STAGED_MARKER, {"schema": 2, "manifest_sha256": sha256(release / MANIFEST_NAME), "tree_verified": True, "directory_fsync": True})
    _fsync_tree(tree)
    _fsync_file(archive_path)
    _fsync_file(release / MANIFEST_NAME)
    _fsync_file(release / STAGED_MARKER)
    _fsync_directory(release)
    _fsync_directory(staging)
    return release


def _evidence_reasons(data: dict, now: float) -> list[str]:
    reasons = []
    if data.get("node") != EXPECTED_NODE:
        reasons.append("evidence is not for node104")
    captured = data.get("captured_at_epoch")
    if not isinstance(captured, (int, float)) or captured > now or now - captured > MAX_PREFLIGHT_AGE_SECONDS:
        reasons.append("fresh trusted timestamp is missing or stale")
    if data.get("service") != EXPECTED_SERVICE or data.get("exec_start") != EXPECTED_EXEC_START:
        reasons.append("service identity or ExecStart is incompatible")
    if data.get("protect_system") != EXPECTED_PROTECT_SYSTEM:
        reasons.append("ProtectSystem=strict is not proven")
    if data.get("filesystem_topology") != "ordinary_directory":
        reasons.append("filesystem topology is not the actual ordinary app directory")
    if data.get("service_stopped") is not True:
        reasons.append("active charging/service stop containment is not proven")
    if data.get("output_state") not in (0, False, "off", "OFF"):
        reasons.append("Output OFF is not independently proven")
    try:
        if abs(float(data.get("measured_voltage_v", 999))) > 0.05 or abs(float(data.get("measured_current_a", 999))) > 0.05:
            reasons.append("fresh independent V/I readback is not zero")
    except (TypeError, ValueError):
        reasons.append("fresh independent V/I readback is invalid")
    if data.get("edge_lease_contained") is not True:
        reasons.append("edge lease containment is not proven")
    if data.get("installed_firmware") != EXPECTED_CANDIDATE_FIRMWARE or data.get("firmware_contract_matched") is not True:
        reasons.append("installed firmware is not the matched candidate edge contract")
    if data.get("independent_sources") != ["systemd", "physical_readback", "edge_lease", "firmware_identity"]:
        reasons.append("independent evidence sources are incomplete")
    return reasons


def preflight(evidence: Path, *, now: float | None = None) -> dict:
    try:
        data = json.loads(evidence.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid preflight evidence: {exc}") from exc
    reasons = _evidence_reasons(data, time.time() if now is None else now)
    if reasons:
        raise RuntimeError("BLOCKED: " + "; ".join(reasons))
    return data


class SimulationLayout:
    def __init__(self, root: Path):
        self.root = root
    @property
    def app(self) -> Path: return self.root / "app"
    @property
    def staging(self) -> Path: return self.root / "staging"
    @property
    def backups(self) -> Path: return self.root / "backups"
    @property
    def journal(self) -> Path: return self.root / JOURNAL_NAME
    @property
    def lock(self) -> Path: return self.root / LOCK_NAME
    @property
    def marker(self) -> Path: return self.root / SIMULATION_MARKER

    def validate_root(self, *, require_marker: bool = False) -> None:
        if self.root.exists() and self.root.is_symlink():
            raise RuntimeError("transaction root must not be a symlink")
        if not self.root.exists() or not self.root.is_dir():
            raise RuntimeError("transaction root must be an existing ordinary directory")
        if require_marker:
            try:
                marker = json.loads(self.marker.read_text(encoding="ascii"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError("transaction root is not an initialized node104 simulation") from exc
            if marker != {"marker": "node104-simulation-v1", "schema": 1}:
                raise RuntimeError("transaction root is not an initialized node104 simulation")
        root = self.root.resolve()
        for child in (self.app, self.staging, self.backups, self.journal, self.lock, self.marker):
            try:
                child.resolve().relative_to(root)
            except ValueError as exc:
                raise RuntimeError("transaction path escapes root") from exc
            if child.is_symlink():
                raise RuntimeError(f"transaction path must not be a symlink: {child}")
        for directory in (self.app, self.staging, self.backups):
            if directory.exists() and directory.stat().st_dev != self.root.stat().st_dev:
                raise RuntimeError(f"{directory.name} is not on the transaction filesystem")


class _HeldLock:
    def __init__(self, path: Path, stream):
        self.path = path
        self.stream = stream

    def close(self, *, remove: bool = False) -> None:
        try:
            if os.name == "nt":
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
        finally:
            self.stream.close()
        if remove and self.path.exists():
            self.path.unlink()


def _acquire_lock(layout: SimulationLayout, *, allow_stale_file: bool = False) -> _HeldLock:
    layout.validate_root()
    try:
        stream = layout.lock.open("x+", encoding="ascii")
        stream.write(str(os.getpid()))
        stream.flush()
        os.fsync(stream.fileno())
    except FileExistsError:
        if not allow_stale_file:
            raise RuntimeError("another deployment transaction owns the journal lock")
        stream = layout.lock.open("r+", encoding="ascii")
    try:
        if os.name == "nt":
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, IOError) as exc:
        stream.close()
        raise RuntimeError("another deployment transaction owns the journal lock") from exc
    return _HeldLock(layout.lock, stream)


def _tree_manifest(root: Path) -> list[dict[str, object]]:
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError(f"unsafe backup tree: {root}")
    result = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            if path.is_symlink():
                raise RuntimeError(f"symlink in backup tree: {path}")
            continue
        result.append({"path": path.relative_to(root).as_posix(), "size": path.stat().st_size, "sha256": sha256(path)})
    return result


def _contained_directory(layout: SimulationLayout, raw: object, name: str, parent: Path) -> Path:
    if not isinstance(raw, str) or not raw:
        raise RuntimeError(f"journal {name} is missing")
    candidate = Path(raw)
    if candidate.is_symlink():
        raise RuntimeError(f"journal {name} is a symlink")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(layout.root.resolve())
        resolved.relative_to(parent.resolve())
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"journal {name} escapes or is missing") from exc
    if resolved.is_symlink() or not resolved.is_dir():
        raise RuntimeError(f"journal {name} is not an ordinary directory")
    return resolved


def _validate_journal(layout: SimulationLayout, record: dict) -> tuple[str, Path, list[dict[str, object]]]:
    if record.get("schema") != 2 or record.get("node") != EXPECTED_NODE or record.get("service") != EXPECTED_SERVICE:
        raise RuntimeError("journal identity/schema is invalid")
    state = record.get("state")
    if state not in {"BACKUP_DURABLE", "SWAP_OLD_RENAMED", "SWAP_NEW_RENAMED", "ROLLBACK_PENDING", "COMMITTED", "ROLLED_BACK"}:
        raise RuntimeError(f"unknown or unsafe journal state: {state!r}")
    _safe_component(record.get("source_sha"), "source SHA")
    backup = _contained_directory(layout, record.get("backup"), "backup", layout.backups)
    expected = record.get("backup_manifest")
    if not isinstance(expected, list) or _tree_manifest(backup) != expected:
        raise RuntimeError("durable backup is missing or corrupted")
    return state, backup, expected


def _write_simulation_marker(layout: SimulationLayout) -> None:
    _write_json(layout.marker, {"schema": 1, "marker": "node104-simulation-v1"})


def _restore_previous(layout: SimulationLayout, backup: Path) -> None:
    previous = layout.root / "app.previous"
    if layout.app.exists():
        if layout.app.is_symlink() or not layout.app.is_dir():
            raise RuntimeError("app is not an ordinary directory")
        shutil.rmtree(layout.app)
    if previous.exists():
        if previous.is_symlink() or not previous.is_dir():
            raise RuntimeError("app.previous is not an ordinary directory")
        os.replace(previous, layout.app)
    else:
        restored = layout.root / f".restore-{os.getpid()}"
        if restored.exists():
            raise RuntimeError("restore scratch path already exists")
        shutil.copytree(backup, restored)
        _fsync_tree(restored)
        os.replace(restored, layout.app)
    _fsync_directory(layout.root)


def _journal(layout: SimulationLayout, state: str, **extra: object) -> None:
    payload = {"schema": 2, "node": EXPECTED_NODE, "service": EXPECTED_SERVICE, "state": state, "updated_at_epoch": time.time(), **extra}
    _write_json(layout.journal, payload, replace=layout.journal.exists())
    _fsync_directory(layout.root)


def recover(layout: SimulationLayout) -> str:
    """Idempotently contain a simulated crash before declaring commit."""
    if not layout.journal.exists():
        return "NO_TRANSACTION"
    layout.validate_root(require_marker=True)
    held = _acquire_lock(layout, allow_stale_file=True)
    try:
        try:
            record = json.loads(layout.journal.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("journal is missing or corrupted") from exc
        if not isinstance(record, dict):
            raise RuntimeError("journal is not an object")
        state, backup, _ = _validate_journal(layout, record)
        if state in {"COMMITTED", "ROLLED_BACK"}:
            return state
        previous = layout.root / "app.previous"
        app_present = layout.app.exists()
        previous_present = previous.exists()
        if state == "BACKUP_DURABLE" and not (app_present or previous_present):
            raise RuntimeError("impossible BACKUP_DURABLE filesystem state")
        if state in {"SWAP_OLD_RENAMED", "SWAP_NEW_RENAMED", "ROLLBACK_PENDING"} and not previous_present:
            raise RuntimeError("impossible swap filesystem state")
        _restore_previous(layout, backup)
        _journal(layout, "ROLLED_BACK", recovered_from=state, source_sha=record["source_sha"], backup=str(backup), backup_manifest=_tree_manifest(backup))
        return "ROLLED_BACK"
    finally:
        held.close(remove=False)


def simulate_transaction(layout: SimulationLayout, staged_tree: Path, source_sha: str, *, crash_after: str | None = None) -> str:
    """Perform a same-FS atomic rename transaction only under ``layout.root``."""
    layout.root.mkdir(parents=True, exist_ok=True)
    _safe_component(source_sha, "source SHA")
    if layout.root.is_symlink() or not layout.root.is_dir():
        raise RuntimeError("transaction root must be an ordinary directory")
    _write_simulation_marker(layout) if not layout.marker.exists() else None
    layout.validate_root(require_marker=True)
    try:
        staged_resolved = staged_tree.resolve(strict=True)
        staged_resolved.relative_to(layout.root.resolve())
    except (OSError, ValueError) as exc:
        raise RuntimeError("staged tree must be contained by transaction root") from exc
    if staged_tree.is_symlink() or not staged_tree.is_dir():
        raise RuntimeError("staged tree must be a real directory")
    if layout.app.exists() and layout.app.is_symlink():
        raise RuntimeError("ordinary app directory cannot be a symlink")
    if staged_tree.stat().st_dev != layout.root.stat().st_dev:
        raise RuntimeError("staged tree and transaction root are not same-FS")
    if layout.app.exists() and layout.app.stat().st_dev != layout.root.stat().st_dev:
        raise RuntimeError("app and transaction root are not same-FS")
    held = _acquire_lock(layout)
    backup = layout.backups / f"backup-{source_sha}"
    crashed = False
    committed = False
    try:
        layout.backups.mkdir(exist_ok=True)
        if backup.exists():
            raise RuntimeError("durable backup already exists for source SHA")
        if not layout.app.is_dir():
            raise RuntimeError("current ordinary app directory is missing")
        shutil.copytree(layout.app, backup)
        _fsync_tree(backup)
        backup_manifest = _tree_manifest(backup)
        _journal(layout, "BACKUP_DURABLE", backup=str(backup), source_sha=source_sha, backup_manifest=backup_manifest)
        if crash_after == "BACKUP_DURABLE":
            crashed = True
            raise RuntimeError("simulated crash after BACKUP_DURABLE")
        os.replace(layout.app, layout.root / "app.previous")
        if crash_after == "SWAP_OLD_RENAMED_BEFORE_JOURNAL":
            crashed = True
            raise RuntimeError("simulated crash after SWAP_OLD_RENAMED before journal")
        _journal(layout, "SWAP_OLD_RENAMED", backup=str(backup), source_sha=source_sha, backup_manifest=backup_manifest)
        if crash_after == "SWAP_OLD_RENAMED":
            crashed = True
            raise RuntimeError("simulated crash after SWAP_OLD_RENAMED")
        os.replace(staged_tree, layout.app)
        if crash_after == "SWAP_NEW_RENAMED_BEFORE_JOURNAL":
            crashed = True
            raise RuntimeError("simulated crash after SWAP_NEW_RENAMED before journal")
        _journal(layout, "SWAP_NEW_RENAMED", backup=str(backup), source_sha=source_sha, backup_manifest=backup_manifest)
        if crash_after == "SWAP_NEW_RENAMED":
            crashed = True
            raise RuntimeError("simulated crash after SWAP_NEW_RENAMED")
        shutil.rmtree(layout.root / "app.previous")
        _fsync_directory(layout.root)
        _journal(layout, "COMMITTED", backup=str(backup), source_sha=source_sha, backup_manifest=backup_manifest)
        committed = True
        return "COMMITTED"
    finally:
        held.close(remove=committed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("manifest", "preflight", "stage", "recover", "simulate"))
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--sha")
    parser.add_argument("--staging", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--root", type=Path)
    args = parser.parse_args(argv)
    if args.phase == "manifest":
        if not args.sha: parser.error("--sha is required")
        print(json.dumps(source_manifest(args.repo, args.sha), indent=2, sort_keys=True))
    elif args.phase == "preflight":
        if not args.evidence: parser.error("--evidence is required")
        preflight(args.evidence)
        print("PREFLIGHT PASS (evidence only; production activation remains unavailable)")
    elif args.phase == "stage":
        if not args.sha or not args.staging: parser.error("--sha and --staging are required")
        print(stage(args.repo, args.sha, args.staging))
    elif args.phase == "recover":
        if not args.root: parser.error("--root is required")
        root = args.root.resolve(strict=True)
        if root == Path(root.anchor) or root.parent == root:
            raise RuntimeError("unsafe recovery root")
        print(recover(SimulationLayout(root)))
    else:
        parser.error("simulate is library-only; use isolated unittest harness")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError, KeyError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2)
