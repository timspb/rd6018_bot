"""Versioned on-disk recipe library, separate from active charge sessions."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from .recipe_schema import Recipe, parse_recipe


class RecipeLibrary:
    def __init__(self, root: str | Path, *, max_voltage_v: float,
                 max_current_a: float) -> None:
        self.root = Path(root)
        self.max_voltage_v = max_voltage_v
        self.max_current_a = max_current_a

    def _file(self, recipe_id: str, version: int) -> Path:
        if not recipe_id or not all(c.isascii() and (c.isalnum() or c in "-_") for c in recipe_id):
            raise ValueError("invalid recipe id")
        if type(version) is not int or version < 1:
            raise ValueError("invalid version")
        return self.root / recipe_id / f"v{version}.json"

    def save(self, document: dict) -> Recipe:
        recipe = parse_recipe(document, max_voltage_v=self.max_voltage_v,
                              max_current_a=self.max_current_a)
        target = self._file(recipe.recipe_id, recipe.version)
        if (target.parent / ".archived").exists():
            raise ValueError("recipe is archived; its history is read-only")
        target.parent.mkdir(parents=True, exist_ok=True)
        data = {"id": recipe.recipe_id, "version": recipe.version,
                "steps": list(recipe.steps)}
        payload = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2)
        # Write a complete, durable staging file first. Expose a version only
        # after the JSON is flushed, without ever replacing an existing version.
        # A crash before os.link cannot expose truncated vN.json to readers.
        staged = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", prefix=".recipe-stage-",
                suffix=".tmp", dir=target.parent, delete=False,
            ) as stream:
                staged = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(staged, target)  # Atomic, no-overwrite publication.
            if os.name == "posix":
                directory_fd = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            if staged is not None:
                staged.unlink(missing_ok=True)
        return recipe

    def load(self, recipe_id: str, version: int) -> Recipe:
        target = self._file(recipe_id, version)
        with target.open(encoding="utf-8") as stream:
            document = json.load(stream)
        recipe = parse_recipe(document, max_voltage_v=self.max_voltage_v,
                              max_current_a=self.max_current_a)
        if (recipe.recipe_id, recipe.version) != (recipe_id, version):
            raise ValueError("recipe identity mismatch")
        return recipe

    def versions(self, recipe_id: str) -> tuple[int, ...]:
        folder = self._file(recipe_id, 1).parent
        return tuple(sorted(int(p.stem[1:]) for p in folder.glob("v[0-9]*.json")
                            if p.stem[1:].isdigit()))
