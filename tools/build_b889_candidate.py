"""Build a portable, inventory-only B889 handoff archive.

The inventory is for reproducibility and review, not integrity authorization.
The full working tree and its real .git metadata are included in the archive.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile
import tarfile


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "B889_CANDIDATE_MANIFEST.json"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, text=True,
                          stdout=subprocess.PIPE).stdout.rstrip("\n")


def file_record(path: Path) -> dict[str, object]:
    relative = path.relative_to(ROOT).as_posix()
    info = path.lstat()
    if path.is_symlink():
        kind, size = "symlink", len(os.readlink(path).encode("utf-8"))
    elif path.is_file():
        kind, size = "file", info.st_size
    else:
        kind, size = "directory", 0
    return {"path": relative, "kind": kind, "mode": info.st_mode & 0o7777,
            "bytes": size}


def inventory() -> dict[str, object]:
    # Include .git because this is a full working-tree handoff. The manifest
    # excludes only itself to avoid self-reference.
    records = [file_record(p) for p in sorted(ROOT.rglob("*")) if p != MANIFEST]
    manifest_relative = MANIFEST.relative_to(ROOT).as_posix()
    untracked = [p for p in git("ls-files", "--others", "--exclude-standard").splitlines()
                 if p != manifest_relative]
    return {
        "schema": "B889_CANDIDATE_INVENTORY_V1",
        "purpose": "reproducible source handoff; not release authorization",
        "git_root": git("rev-parse", "--show-toplevel"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "head": git("rev-parse", "HEAD"),
        "staged_paths": git("diff", "--cached", "--name-only").splitlines(),
        "tracked_worktree_paths": git("diff", "--name-only").splitlines(),
        "untracked_paths": untracked,
        "entries": records,
        "entry_count": len(records),
        "cryptographic_digests": "not collected or used",
    }


def build(archive: Path) -> None:
    document = inventory()
    MANIFEST.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8", newline="\n")
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix="b889-", suffix=".tar", dir=archive.parent,
                                     delete=False) as temp_tar:
        tar_path = Path(temp_tar.name)
    try:
        with tarfile.open(tar_path, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for path in [ROOT, *sorted(ROOT.rglob("*"))]:
                relative = "." if path == ROOT else path.relative_to(ROOT).as_posix()
                info = tar.gettarinfo(str(path), arcname=f"B889-candidate/{relative}")
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mtime = 0
                if info.isfile():
                    with path.open("rb") as stream:
                        tar.addfile(info, stream)
                else:
                    tar.addfile(info)
        with tar_path.open("rb") as source, archive.open("wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0,
                               compresslevel=9) as gz:
                while chunk := source.read(1024 * 1024):
                    gz.write(chunk)
    finally:
        tar_path.unlink(missing_ok=True)
    print(f"manifest={MANIFEST}")
    print(f"archive={archive}")
    print(f"entries={document['entry_count']}")
    print(f"head={document['head']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    build(args.archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
