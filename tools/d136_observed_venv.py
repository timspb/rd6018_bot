"""D136: read-only observed environment baseline, NOT historical candidate evidence.

No writes, service lifecycle operations or hardware control. The observed venv
must never be represented as the absent D090 candidate_inventory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def inventory(root: Path) -> dict[str, object]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("invalid environment directory")
    rows = []
    for p in sorted(root.rglob("*")):
        relative = p.relative_to(root).as_posix()
        mode = p.lstat().st_mode
        if stat.S_ISLNK(mode):
            target = os.readlink(p)
            # Record rather than follow symlinks. No link payload disclosure.
            rows.append([relative, "link", hashlib.sha256(os.fsencode(target)).hexdigest()])
        elif stat.S_ISDIR(mode):
            rows.append([relative, "directory"])
        elif stat.S_ISREG(mode):
            rows.append([relative, "file", p.stat().st_size, bool(mode & stat.S_IXUSR), file_hash(p)])
        else:
            raise ValueError("unsupported special filesystem entry: " + relative)
    canonical = json.dumps(rows, separators=(",", ":"), ensure_ascii=True)
    return {"entries": len(rows), "regular_files": sum(x[1] == "file" for x in rows),
            "symlinks": sum(x[1] == "link" for x in rows),
            "tree_sha256": hashlib.sha256(canonical.encode("ascii")).hexdigest()}


def collect(root: Path, pid: int | None) -> dict[str, object]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("invalid installation root")
    app = root / "app"
    venv = root / "venv"
    d090 = root / "D090_TRANSACTION.json"
    marker = root / ".deploy_sha"
    if d090.is_symlink() or marker.is_symlink():
        raise ValueError("unsafe deployment journal or marker")
    journal_before = file_hash(d090)
    marker_before = file_hash(marker)
    if pid is not None:
        argv = (Path("/proc") / str(pid) / "cmdline").read_bytes().split(bytes([0]))
        if str(app / "bot.py").encode() not in argv:
            raise ValueError("PID not bound to installed application")
    venv_before = inventory(venv)
    venv_after = inventory(venv)
    if venv_before != venv_after:
        raise RuntimeError("venv changed during observation")
    if file_hash(d090) != journal_before or file_hash(marker) != marker_before:
        raise RuntimeError("deployment metadata changed during observation")
    journal = json.loads(d090.read_text(encoding="utf-8"))
    return {
        "schema": "D136_OBSERVED_VENV_V1",
        "status": "OBSERVED_ONLY_NOT_RELEASE_ADMISSION",
        "venv": venv_after,
        "d090": {"phase": journal.get("phase"),
                 "transaction": journal.get("transaction"),
                 "candidate_inventory_present": isinstance(journal.get("candidate_inventory"), dict),
                 "journal_sha256": journal_before,
                 "marker_sha256": marker_before},
        "process_pid": pid,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/opt/services/rd6018-bot"))
    parser.add_argument("--pid", type=int)
    args = parser.parse_args()
    print(json.dumps(collect(args.root, args.pid), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()