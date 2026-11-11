"""Source inventory for production AST audits in a Git checkout or verified release stage.

No production/runtime imports and no recursive scan of independent worktrees.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path, PurePosixPath
import subprocess


@lru_cache(maxsize=8)
def source_inventory(root: Path) -> tuple[Path, ...]:
    """Return paths relative to the current checkout or verified staged tree.

    A source-only release has no .git. Its adjacent STAGED_OK is bound to the
    complete RELEASE_MANIFEST.json. Never silently broaden to rglob().
    """
    root = root.resolve()
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=root, capture_output=True, text=True, check=False,
    )
    if result.returncode == 0 and Path(result.stdout.strip()).resolve() == root:
        entries = subprocess.check_output(
            ["git", "ls-files", "-z"], cwd=root,
        ).split(bytes([0]))
        paths = tuple(
            Path(raw.decode("utf-8")) for raw in entries if raw
        )
    else:
        manifest_path = root.parent / "RELEASE_MANIFEST.json"
        marker_path = root.parent / "STAGED_OK"
        if root.name != "tree" or not manifest_path.is_file() or not marker_path.is_file():
            raise RuntimeError("source audit requires Git checkout or verified release stage")
        manifest_bytes = manifest_path.read_bytes()
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        if (marker.get("tree_verified") is not True
                or marker.get("manifest_sha256") != hashlib.sha256(manifest_bytes).hexdigest()):
            raise RuntimeError("release source inventory verification missing")
        manifest = json.loads(manifest_bytes)
        entries = manifest.get("files")
        if not isinstance(entries, list) or not entries:
            raise RuntimeError("release source manifest is empty or invalid")
        paths = tuple(Path(item["path"]) for item in entries)
    if not paths:
        raise RuntimeError("source audit cannot accept empty inventory")
    if len(set(paths)) != len(paths):
        raise RuntimeError("source audit inventory contains duplicates")
    for path in paths:
        posix = PurePosixPath(path.as_posix())
        if (posix.is_absolute() or ".." in posix.parts or path.is_absolute()
                or not path.parts or (root / path).is_symlink()
                or not (root / path).is_file()):
            raise RuntimeError(f"unsafe source inventory path: {path}")
    if Path("bot.py") not in paths:
        raise RuntimeError("source inventory is missing production entrypoint")
    return tuple(sorted(paths, key=lambda path: path.as_posix()))


def production_python_sources(root: Path):
    """Yield paths for tracked production Python, excluding test code."""
    for relative in source_inventory(root):
        if relative.suffix == ".py" and "tests" not in relative.parts:
            yield relative, root / relative
