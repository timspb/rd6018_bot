"""D138: non-mutating candidate admission preflight.

Produces evidence only. Neither a new transaction nor activation is
authorized by this helper. Legacy D090 and production state are immutable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess

from tools.d133_live_byte_baseline import sha256
from tools.d136_observed_venv import inventory as inventory_venv
from tools.d137_observed_preimage import observed_preimage

MIN_FREE_BYTES = 256 * 1024 * 1024


def inspect_candidate(*, root: Path, stage: Path, pid: int,
                      source_sha: str, preimage_sha256: str) -> dict[str, object]:
    if not (len(source_sha) == 40 and all(c in "0123456789abcdef" for c in source_sha)):
        raise ValueError("source SHA invalid")
    if not (len(preimage_sha256) == 64 and all(c in "0123456789abcdef" for c in preimage_sha256)):
        raise ValueError("preimage digest invalid")
    if stage.is_symlink() or not stage.is_dir():
        raise ValueError("candidate staging directory invalid")
    actual_preimage = observed_preimage(root, pid=pid)
    if actual_preimage["preimage_sha256"] != preimage_sha256:
        raise ValueError("installed composite preimage drift")
    manifest_path = stage / "RELEASE_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("schema") != "D138_STAGED_SOURCE_V1"
            or manifest.get("source_sha") != source_sha
            or type(manifest.get("manifest_entries")) is not list
            or manifest.get("files") != len(manifest["manifest_entries"])):
        raise ValueError("source candidate manifest invalid")
    tree = stage / "tree"
    if tree.is_symlink() or not tree.is_dir():
        raise ValueError("candidate source tree invalid")
    expected = set()
    for item in manifest["manifest_entries"]:
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "size", "mode"}:
            raise ValueError("source inventory schema invalid")
        p = PurePosixPath(item["path"])
        if p.is_absolute() or ".." in p.parts or not p.parts:
            raise ValueError("unsafe candidate path")
        relative = p.as_posix()
        if relative in expected:
            raise ValueError("duplicate candidate path")
        expected.add(relative)
        file = tree.joinpath(*p.parts)
        if (file.is_symlink() or not file.is_file()
                or file.stat().st_size != item["size"]
                or file.stat().st_mode & 0o777 != item["mode"]
                or sha256(file) != item["sha256"]):
            raise ValueError("candidate source byte/mode mismatch: " + relative)
    actual = set()
    for item in tree.rglob("*"):
        if item.is_symlink():
            raise ValueError("candidate tree symlink rejected")
        if item.is_file():
            actual.add(item.relative_to(tree).as_posix())
    if actual != expected:
        raise ValueError("candidate source file set mismatch")
    venv = stage / "venv"
    if venv.is_symlink() or not (venv / "bin/python").is_file():
        raise ValueError("candidate Python environment incomplete")
    cmd = [str(venv / "bin/python"), "-m", "pip", "check"]
    verdict = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=45)
    if verdict.returncode:
        raise ValueError("candidate dependencies not installed or inconsistent")
    version = subprocess.run([str(venv / "bin/python"), "-c", "import sys; print(sys.version_info[:2])"],
                             check=True, capture_output=True, text=True, timeout=15)
    if version.stdout.strip() != "(3, 11)":
        raise ValueError("candidate Python version not 3.11")
    venv_record = inventory_venv(venv)
    if venv_record["regular_files"] < 100:
        raise ValueError("candidate environment too small")
    if shutil.disk_usage(stage).free < MIN_FREE_BYTES:
        raise ValueError("less than reserved 256 MiB disk capacity")
    payload = {
        "schema": "D138_CANDIDATE_PREPARED_V1", "status": "SOURCE_AND_VENV_PREPARED_NOT_ACTIVATED",
        "source_sha": source_sha, "observed_preimage_sha256": preimage_sha256,
        "source_archive_sha256": manifest["source_archive_sha256"],
        "source_manifest_sha256": sha256(manifest_path),
        "source_files": len(expected), "venv": venv_record,
        "legacy_d090_untouched": True, "admitted_for_activation": False
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    payload["candidate_identity_sha256"] = hashlib.sha256(encoded.encode("ascii")).hexdigest()
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/opt/services/rd6018-bot"))
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--preimage-sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(inspect_candidate(root=args.root, stage=args.stage, pid=args.pid,
                                      source_sha=args.source_sha, preimage_sha256=args.preimage_sha256),
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
