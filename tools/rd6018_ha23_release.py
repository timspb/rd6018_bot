#!/usr/bin/env python3
"""Stage/verify/install the canonical 2.3 ESPHome HA source, never flash here."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time

VERSION = "2.3-ha-canonical"
FILES = ("rd6018.yaml", "packages/rd6018_safety_lease.yaml",
         "packages/rd6018_telemetry_v2.yaml",
         "packages/rd6018_intrinsic_safety.yaml",
         "packages/rd6018_live_adoption.yaml")
LOCK = "RD6018_23_SOURCE_LOCK.json"

def digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

def safe(p: Path) -> Path:
    if p.is_symlink():
        raise ValueError(f"symlink forbidden: {p}")
    return p

def audit_source(src: Path) -> dict:
    y = safe(src / "rd6018.yaml").read_text(encoding="utf-8")
    if y.count('version: "' + VERSION + '"') != 1:
        raise ValueError("wrong HA project version; no release")
    if 'min_version: "2026.9.1"' not in y:
        raise ValueError("missing minimum ESPHome builder")
    if 'name: "Firmware Canonical Release"' not in y:
        raise ValueError("release Native identity missing")
    for file in FILES:
        if not safe(src / file).is_file():
            raise ValueError(f"missing source {file}")
        if file.startswith("packages/") and f"!include {file}" not in y:
            raise ValueError(f"unreferenced safety package {file}")
    return {"schema": 1, "release": VERSION,
            "source_files_sha256": {p: digest(src / p) for p in FILES}}

def verify(src: Path) -> dict:
    record = json.loads(safe(src / LOCK).read_text(encoding="utf-8"))
    actual = audit_source(src)
    if record != actual:
        raise ValueError("RELEASE LOCK MISMATCH; refuse compile/install")
    return record

def stage(src: Path, target: Path) -> None:
    record = audit_source(src)
    if target.exists():
        raise ValueError("stage must be a fresh path")
    target.mkdir(parents=True)
    for rel in FILES:
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / rel, dest)
    (target / LOCK).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
    verify(target)
    print(json.dumps({"stage": str(target), "release": VERSION,
                      "files": record["source_files_sha256"]}, sort_keys=True))

def atomic_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    safe(dst)
    temp = dst.with_name(dst.name + ".new-rd6018-23")
    if temp.exists():
        raise ValueError("stale incomplete copy: " + str(temp))
    shutil.copy2(src, temp)
    if digest(src) != digest(temp):
        raise ValueError("copy checksum mismatch: " + str(dst))
    os.replace(temp, dst)

def install(stage_dir: Path, ha_dir: Path) -> None:
    record = verify(stage_dir)
    ha_dir = ha_dir.resolve(strict=True)
    if not (ha_dir / "secrets.yaml").is_file():
        raise ValueError("HA ESPHome secrets.yaml not found; refuse install")
    if not (ha_dir / "rd6018.yaml").is_file():
        raise ValueError("Existing HA device YAML not found; refuse new device")
    if ha_dir.is_symlink():
        raise ValueError("HA target must not be symlink")
    backup = ha_dir / "rd6018_release_backups" / ("pre-23-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
    if backup.exists():
        raise ValueError("backup collision")
    backup.mkdir(parents=True)
    for rel in FILES:
        p = safe(ha_dir / rel)
        if p.exists():
            dest = backup / (rel + ".bak")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)
    (backup / "README.txt").write_text("HA ESPHome pre-2.3 source backup. Secrets never copied.\n")
    for rel in FILES[1:]:
        atomic_copy(stage_dir / rel, ha_dir / rel)
    atomic_copy(stage_dir / FILES[0], ha_dir / FILES[0])
    atomic_copy(stage_dir / LOCK, ha_dir / LOCK)
    verify(ha_dir)
    print(json.dumps({"installed_source_only": True, "ha_dir": str(ha_dir),
                      "backup": str(backup), "release": record["release"],
                      "firmware_flashed": False}, sort_keys=True))

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("stage", "verify", "install"))
    parser.add_argument("--source", type=Path)
    parser.add_argument("--stage-dir", type=Path)
    parser.add_argument("--ha-dir", type=Path)
    args = parser.parse_args()
    if args.action == "stage":
        if not args.source or not args.stage_dir:
            parser.error("stage needs --source and --stage-dir")
        stage(args.source, args.stage_dir)
    elif args.action == "verify":
        if not args.ha_dir:
            parser.error("verify needs --ha-dir")
        print(json.dumps(verify(args.ha_dir), sort_keys=True))
    else:
        if not args.stage_dir or not args.ha_dir:
            parser.error("install needs --stage-dir and --ha-dir")
        install(args.stage_dir, args.ha_dir)

if __name__ == "__main__":
    main()
