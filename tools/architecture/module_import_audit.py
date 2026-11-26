"""Passive, deterministic AST inventory of tracked production import edges.

This tool observes imports only. It never imports or executes repository code and
does not enforce architectural policy.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping


EDGE_KINDS = ("eager", "type_checking", "deferred")
EXCLUDED_PARTS = {"tests", "tools", ".worktrees", ".venv"}


def _checked_path(path: str | os.PathLike[str]) -> PurePosixPath:
    """Validate a repository-relative POSIX path; reject traversal and absolutes."""
    raw = str(path).replace("\\", "/")
    p = PurePosixPath(raw)
    if p.is_absolute() or not raw or any(part in {"..", ""} for part in raw.split("/")):
        raise ValueError(f"unsafe repository path: {path!s}")
    if p.as_posix() == ".":
        raise ValueError(f"unsafe repository path: {path!s}")
    return p


def _module_name(path: PurePosixPath) -> str:
    parts = list(path.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _base_package(module: str, is_package: bool) -> str:
    if is_package:
        return module
    return module.rpartition(".")[0]


def _resolve_from(node: ast.ImportFrom, module: str, is_package: bool,
                  known: set[str]) -> list[str]:
    package = _base_package(module, is_package)
    try:
        if node.level:
            base = __import__("importlib.util", fromlist=["resolve_name"]).resolve_name(
                "." * node.level + (node.module or ""), package
            )
        else:
            base = node.module or ""
    except (ImportError, ValueError):
        return []
    if not base:
        return []
    result = []
    for alias in node.names:
        if alias.name == "*":
            candidate = base
        else:
            candidate = base + "." + alias.name
        result.append(candidate if candidate in known else base)
    return result


def scan_file(path: str | os.PathLike[str], source: str,
              known_modules: Iterable[str] = ()) -> dict[str, object]:
    """Return import observations for one source file without executing it."""
    relative = _checked_path(path)
    module = _module_name(relative)
    is_package = relative.name == "__init__.py"
    known = set(known_modules)
    found: list[dict[str, object]] = []
    dynamic: list[dict[str, object]] = []
    tree = ast.parse(source, filename=relative.as_posix())

    def record(target: str, line: int, kind: str, form: str) -> None:
        if target in known and target != module:
            found.append({"source": module, "target": target, "kind": kind,
                          "form": form, "line": line, "path": relative.as_posix()})

    def visit(node: ast.AST, context: str = "eager") -> None:
        if isinstance(node, ast.If) and _is_type_checking(node.test):
            for child in node.body:
                visit(child, "type_checking")
            for child in node.orelse:
                visit(child, context)
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for child in node.body:
                visit(child, "deferred")
            # Decorators/defaults/bases execute when the declaration is evaluated.
            for child in (*node.decorator_list, *getattr(node, "bases", ()),
                          *getattr(node, "keywords", ())):
                visit(child, context)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in (*node.args.defaults, *node.args.kw_defaults):
                    if child is not None:
                        visit(child, context)
            return
        if isinstance(node, ast.Import):
            for alias in node.names:
                record(alias.name, node.lineno, context, "import")
            return
        if isinstance(node, ast.ImportFrom):
            for target in _resolve_from(node, module, is_package, known):
                record(target, node.lineno, context, "from")
            return
        if isinstance(node, ast.Call) and _is_dynamic_import(node):
            arg = node.args[0] if node.args else None
            value = arg.value if isinstance(arg, ast.Constant) and isinstance(arg.value, str) else None
            dynamic.append({"source": module, "target": value,
                            "line": node.lineno, "path": relative.as_posix()})
        for child in ast.iter_child_nodes(node):
            visit(child, context)

    for statement in tree.body:
        visit(statement)
    found.sort(key=lambda e: (str(e["source"]), str(e["target"]), str(e["kind"]),
                              int(e["line"]), str(e["form"])))
    dynamic.sort(key=lambda e: (int(e["line"]), str(e["target"])))
    return {"module": module, "edges": found, "dynamic_imports": dynamic}


def _is_type_checking(node: ast.AST) -> bool:
    return ((isinstance(node, ast.Name) and node.id == "TYPE_CHECKING") or
            (isinstance(node, ast.Attribute) and node.attr == "TYPE_CHECKING"))


def _is_dynamic_import(node: ast.Call) -> bool:
    f = node.func
    return ((isinstance(f, ast.Name) and f.id == "__import__") or
            (isinstance(f, ast.Attribute) and f.attr == "import_module"))


def _sccs(graph: Mapping[str, set[str]]) -> list[list[str]]:
    index = 0
    indices: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    active: set[str] = set()
    result: list[list[str]] = []

    def strong(v: str) -> None:
        nonlocal index
        indices[v] = low[v] = index
        index += 1
        stack.append(v)
        active.add(v)
        for w in sorted(graph.get(v, set())):
            if w not in indices:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in active:
                low[v] = min(low[v], indices[w])
        if low[v] == indices[v]:
            group = []
            while True:
                w = stack.pop()
                active.remove(w)
                group.append(w)
                if w == v:
                    break
            if len(group) > 1 or v in graph.get(v, set()):
                result.append(sorted(group))

    for vertex in sorted(graph):
        if vertex not in indices:
            strong(vertex)
    return sorted(result)


def scan_graph(root: str | os.PathLike[str],
               tracked_paths: Iterable[str] | None = None) -> dict[str, object]:
    """Scan tracked checkout Python files; absent tracked paths are skipped."""
    root_path = Path(root).resolve()
    if tracked_paths is None:
        completed = subprocess.run(["git", "ls-files", "-z", "--", "*.py"],
                                   cwd=root_path, check=True, stdout=subprocess.PIPE)
        paths = [p.decode("utf-8", "surrogateescape")
                 for p in completed.stdout.split(b"\0") if p]
    else:
        paths = list(tracked_paths)
    normalized: list[tuple[str, Path]] = []
    for raw in paths:
        rel = _checked_path(raw)
        candidate = root_path.joinpath(*rel.parts)
        try:
            candidate.resolve().relative_to(root_path)
        except ValueError as exc:
            raise ValueError(f"path escapes repository: {raw}") from exc
        if any(part in EXCLUDED_PARTS for part in rel.parts):
            continue
        if rel.suffix != ".py" or not candidate.is_file():
            continue
        normalized.append((rel.as_posix(), candidate))
    normalized.sort(key=lambda item: item[0])
    modules = {_module_name(PurePosixPath(rel)) for rel, _ in normalized}
    observations = [scan_file(rel, path.read_text(encoding="utf-8"), modules)
                    for rel, path in normalized]
    eager = [e for obs in observations for e in obs["edges"] if e["kind"] == "eager"]
    by_kind = {kind: sorted((e for obs in observations for e in obs["edges"]
                             if e["kind"] == kind),
                            key=lambda e: (e["source"], e["target"], e["line"], e["path"]))
               for kind in EDGE_KINDS}
    graph: dict[str, set[str]] = {m: set() for m in modules}
    for edge in eager:
        graph[str(edge["source"])].add(str(edge["target"]))
    return {
        "schema": "rd6018.module_import_audit.v1",
        "policy": "passive_observation_only",
        "root": str(root_path),
        "counts": {"tracked_existing_production_py": len(normalized),
                   "eager_edges": len(by_kind["eager"]),
                   "type_checking_edges": len(by_kind["type_checking"]),
                   "deferred_edges": len(by_kind["deferred"]),
                   "dynamic_import_calls": sum(len(o["dynamic_imports"]) for o in observations)},
        "edges": by_kind,
        "dynamic_imports": sorted((d for o in observations for d in o["dynamic_imports"]),
                                   key=lambda d: (d["source"], d["line"], str(d["target"]))),
        "eager_cycles": _sccs(graph),
        "modules": sorted(modules),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="repository root (default: cwd)")
    parser.add_argument("--output", help="write JSON report to this path; stdout otherwise")
    args = parser.parse_args(argv)
    report = scan_graph(args.root)
    rendered = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
