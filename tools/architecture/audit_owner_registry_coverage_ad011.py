"""Read-only deterministic audit of AD010 registry coverage versus checkout files."""
from __future__ import annotations

import argparse
import ast
import csv
import os
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "tests/fixtures/architecture/ownership_history/mod_p1_owner_decisions_ad010_20261113.csv"
OUTPUT = ROOT / ".recipe-studio-local/mod_p1_registry_coverage_ad011_20261113.csv"
BASELINE_PATHS = 481
BASELINE_APPROVED = 21
FIELDS = ["path", "git_status", "ignored", "registry_membership", "source_import_consumers",
          "proposed_is_production", "reason", "risk", "owner_approval"]
EXCLUDED_DIRS = {"tests", "tools", "docs", ".worktrees", ".venv", "venv", ".recipe-studio-local",
                 "__pycache__", "node_modules", "build", "dist", "site-packages"}


def _git(root: Path, *args: str) -> list[str]:
    raw = subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE)
    return [x.decode("utf-8", "surrogateescape") for x in raw.split(b"\0") if x]


def _is_ignored(root: Path, path: str) -> bool:
    result = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", "--", path],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


def _module(path: str) -> str:
    p = PurePosixPath(path)
    name = p.with_suffix("")
    parts = list(name.parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports(root: Path, paths: list[str], candidates: set[str]) -> dict[str, list[str]]:
    module_to_path = {_module(p): p for p in paths if p.endswith(".py")}
    candidate_modules = {_module(p): p for p in candidates}
    consumers: dict[str, set[str]] = {p: set() for p in candidates}
    for path in paths:
        if not path.endswith(".py") or path not in module_to_path.values():
            continue
        source_path = root / path
        try:
            tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=path)
        except (OSError, UnicodeError, SyntaxError):
            continue
        srcmod = _module(path)
        is_pkg = PurePosixPath(path).name == "__init__.py"
        for node in ast.walk(tree):
            targets: list[str] = []
            if isinstance(node, ast.Import):
                targets.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    package = srcmod if is_pkg else srcmod.rpartition(".")[0]
                    try:
                        import importlib.util
                        base = importlib.util.resolve_name("." * node.level + (node.module or ""), package)
                    except (ImportError, ValueError):
                        continue
                else:
                    base = node.module or ""
                if base:
                    targets.append(base)
                    targets.extend(base + "." + a.name for a in node.names if a.name != "*")
            for target in targets:
                found = candidate_modules.get(target)
                if found is None:
                    # Parent/package imports can refer to a candidate module's package.
                    found = candidate_modules.get(target.rpartition(".")[0])
                if found and found != path:
                    consumers[found].add(f"{path}:{node.lineno}")
    return {p: sorted(v) for p, v in consumers.items()}


def _excluded(path: str) -> tuple[str, str] | None:
    parts = PurePosixPath(path).parts
    if any(part in EXCLUDED_DIRS for part in parts):
        part = next(part for part in parts if part in EXCLUDED_DIRS)
        return "no", f"excluded non-production scope: {part}"
    if any(part.startswith(".") for part in parts):
        return "no", "hidden local/configuration path; not in production source inventory"
    low = path.lower()
    if any(token in PurePosixPath(low).name for token in (".bak", ".backup", ".orig", ".rej", "~")):
        return "no", "backup or patch artifact"
    if ".pyc" in low or "__pycache__" in parts:
        return "no", "generated Python bytecode"
    if parts and (parts[0].startswith("worktree") or ".worktree" in parts[0].lower()):
        return "no", "shadow/generated worktree"
    return None


def audit(root: Path, registry_path: Path, *, tracked_paths: set[str] | None = None,
          untracked_paths: set[str] | None = None, ignored_paths: set[str] | None = None) -> tuple[list[dict[str, str]], dict[str, int]]:
    root = root.resolve()
    with registry_path.open(encoding="utf-8-sig", newline="") as stream:
        registry_rows = list(csv.DictReader(stream))
    registry = {r["path"]: r for r in registry_rows}
    if len(registry_rows) != BASELINE_PATHS or len(registry) != BASELINE_PATHS:
        raise ValueError(f"AD010 registry must contain exactly {BASELINE_PATHS} unique paths")
    approvals = sum(bool(r.get("approved_primary_owner") or r.get("AD008_approved_primary_owner") or
                          r.get("ad010_primary_owner")) for r in registry_rows)
    if approvals != BASELINE_APPROVED:
        raise ValueError(f"AD010 registry must retain exactly {BASELINE_APPROVED} approved primary owners")
    tracked = set(tracked_paths) if tracked_paths is not None else set(_git(root, "ls-files", "-z"))
    untracked = set(untracked_paths) if untracked_paths is not None else set(_git(root, "ls-files", "--others", "--exclude-standard", "-z"))
    present = {p for p in tracked | untracked if (root / p).is_file()}
    candidates = {p for p in present if p.endswith(".py")}
    # Git intentionally omits ignored paths from --others. Resolve local targets
    # of imports from checkout Python sources so imported ignored modules surface.
    source_paths = sorted(p for p in candidates if p in registry or not _excluded(p))
    import_paths = source_paths
    for source in source_paths:
        try:
            tree = ast.parse((root / source).read_text(encoding="utf-8"), filename=source)
        except (OSError, UnicodeError, SyntaxError):
            continue
        for node in ast.walk(tree):
            targets = [a.name for a in node.names] if isinstance(node, ast.Import) else []
            if isinstance(node, ast.ImportFrom) and node.module and not node.level:
                targets.append(node.module)
            for target in targets:
                rel = target.replace(".", "/")
                for candidate in (rel + ".py", rel + "/__init__.py"):
                    full = root / candidate
                    if full.is_file() and ((candidate in ignored_paths) if ignored_paths is not None else _is_ignored(root, candidate)):
                        candidates.add(candidate)
                        present.add(candidate)
                        untracked.add(candidate)
    consumers = _imports(root, import_paths, candidates)
    rows = []
    all_paths = sorted(set(registry) | present)
    for path in all_paths:
        in_registry = path in registry
        exists = (root / path).is_file()
        ignored = ((path in ignored_paths) if ignored_paths is not None else
                   (_is_ignored(root, path) if exists and path not in tracked else False))
        status = "tracked" if path in tracked else "untracked" if path in untracked else "missing"
        membership = "present" if in_registry else "undiscovered"
        reason = "registered production path; registry membership is baseline evidence" if in_registry else ""
        proposed, risk = ("yes", "baseline") if in_registry else ("no", "low")
        if not exists:
            proposed, reason, risk = "uncertain", "registered path is missing from current checkout" if in_registry else "candidate vanished before inspection", "high"
        elif not in_registry:
            excluded = _excluded(path)
            if excluded:
                proposed, reason = excluded
                risk = "low"
            elif ignored:
                proposed = "uncertain"
                reason = "ignored Python file outside known exclusions; usage/reachability requires review"
                risk = "high"
            elif path in candidates:
                if consumers.get(path):
                    proposed = "yes" if status == "tracked" else "uncertain"
                    reason = "Python source outside exclusion scope with production-source import consumer(s); registry gap" if status == "tracked" else "untracked Python source imported from checkout source; probable registry gap"
                    risk = "high"
                elif status == "untracked":
                    proposed, reason, risk = "uncertain", "untracked Python source outside exclusion scope; production use not proven", "medium"
                else:
                    proposed, reason, risk = "uncertain", "tracked Python source outside exclusion scope but no static import consumer observed", "medium"
            else:
                proposed, reason, risk = "no", "non-Python file; inventory scope is production Python modules", "low"
        refs = "; ".join(consumers.get(path, []))
        rows.append({"path": path, "git_status": status, "ignored": "yes" if ignored else "no",
                     "registry_membership": membership, "source_import_consumers": refs,
                     "proposed_is_production": proposed, "reason": reason, "risk": risk,
                     "owner_approval": "NEVER_ASSIGNED"})
    counts = {"registry_paths": len(registry), "registry_approved": approvals,
              "tracked_git_paths": len(tracked), "untracked_git_paths": len(untracked),
              "present_python_candidates": len(candidates),
              "registry_missing": sum(r["registry_membership"] == "present" and r["git_status"] == "missing" for r in rows),
              "undiscovered_probable": sum(r["registry_membership"] == "undiscovered" and (r["proposed_is_production"] == "yes" or (r["git_status"] == "untracked" and bool(r["source_import_consumers"]))) for r in rows),
              "uncertain": sum(r["proposed_is_production"] == "uncertain" for r in rows),
              "ignored_python": sum(r["ignored"] == "yes" and r["path"].endswith(".py") for r in rows)}
    return rows, counts


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    rows, counts = audit(args.root, args.registry)
    write_csv(args.output, rows)
    print("\n".join(f"{key}={value}" for key, value in counts.items()))
    print(f"csv={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
