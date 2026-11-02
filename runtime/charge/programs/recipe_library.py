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
        target.parent.mkdir(parents=True, exist_ok=True)
        data = {"id": recipe.recipe_id, "version": recipe.version,
                "steps": list(recipe.steps)}
        payload = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2)
        # Existing versions cannot be overwritten: historical experiments remain reproducible.
        with target.open("x", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
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
