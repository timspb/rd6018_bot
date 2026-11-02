"""Non-destructive catalog management for immutable recipe versions."""
from __future__ import annotations

import json
from pathlib import Path

from .recipe_library import RecipeLibrary
from .recipe_schema import Recipe


class RecipeCatalog:
    def __init__(self, library: RecipeLibrary):
        self.library = library

    def list_recipes(self) -> tuple[str, ...]:
        root = self.library.root
        if not root.exists():
            return ()
        return tuple(sorted(p.name for p in root.iterdir()
                            if p.is_dir() and self.library.versions(p.name)))

    def duplicate(self, source_id: str, version: int, new_id: str) -> Recipe:
        source = self.library.load(source_id, version)
        return self.library.save({
            "id": new_id, "version": 1,
            "steps": [dict(step) for step in source.steps],
        })

    def next_version(self, recipe_id: str, steps: list[dict]) -> Recipe:
        versions = self.library.versions(recipe_id)
        if not versions:
            raise FileNotFoundError("recipe not found; create version 1 first")
        return self.library.save({
            "id": recipe_id, "version": max(versions) + 1, "steps": steps,
        })

    def archive(self, recipe_id: str) -> None:
        """Archive recipe without removing historical versions."""
        versions = self.library.versions(recipe_id)
        if not versions:
            raise FileNotFoundError("recipe not found")
        path = self.library.root / recipe_id / ".archived"
        with path.open("x", encoding="utf-8") as output:
            output.write("archived\n")

    def active_recipes(self) -> tuple[str, ...]:
        return tuple(name for name in self.list_recipes()
                     if not (self.library.root / name / ".archived").exists())
