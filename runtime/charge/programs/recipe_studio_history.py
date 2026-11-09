"""Recipe Studio read-only history and archive over canonical immutable libraries.

No actuator or session access. Archive is one-way, preserves historical bytes.
"""
from __future__ import annotations
import difflib
import json
from pathlib import Path

from runtime.charge.programs.recipe_catalog import RecipeCatalog


def history(library, kind: str) -> list[dict]:
    if kind == "step":
        names = RecipeCatalog(library).list_recipes()
    elif kind == "native":
        names = library.list_drafts()
    else:
        raise ValueError("unknown recipe kind")
    result = []
    for name in names:
        versions = library.versions(name)
        if not versions:
            continue
        result.append({
            "id": name,
            "versions": list(versions),
            "latest": versions[-1],
            "archived": (library.root / name / ".archived").exists(),
        })
    return result


def _validated_identity(name, version):
    if type(name) is not str or type(version) is not int or version < 1:
        raise ValueError("invalid identity or version")
    return name, version


def load_document(library, kind: str, name: str, version: int) -> dict:
    name, version = _validated_identity(name, version)
    # Reuse library's identity and canonical schema validation.
    if kind == "step":
        recipe = library.load(name, version)
        return {"id": name, "version": version, "steps": list(recipe.steps)}
    if kind == "native":
        draft = library.load(name, version)
        return {"name": name, "version": version, "draft": draft.as_document()}
    raise ValueError("unknown recipe kind")


def compare(library, kind: str, name: str, left: int, right: int) -> dict:
    # No source files or arbitrary paths in this interface.
    first = load_document(library, kind, name, left)
    second = load_document(library, kind, name, right)
    def canonical(obj):
        result = dict(obj)
        result.pop("version", None)
        return json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
    diff = list(difflib.unified_diff(
        canonical(first), canonical(second), fromfile=f"v{left}", tofile=f"v{right}",
        lineterm="",
    ))
    return {"id": name, "left": left, "right": right, "changed": bool(diff),
            "diff": "\n".join(diff)[:24000]}


def archive(library, kind: str, name: str) -> dict:
    if type(name) is not str or not name:
        raise ValueError("invalid name")
    if kind == "step":
        RecipeCatalog(library).archive(name)
    elif kind == "native":
        library.archive(name)
    else:
        raise ValueError("unknown recipe kind")
    return {"id": name, "archived": True}
