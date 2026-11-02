"""Immutable step editing; every edit creates a new recipe version."""
from __future__ import annotations
from copy import deepcopy
from .recipe_catalog import RecipeCatalog


def edit_step(catalog: RecipeCatalog, recipe_id: str, source_version: int,
              index: int, *, field: str, value: float):
    latest = catalog.library.versions(recipe_id)
    if not latest or source_version != latest[-1]:
        raise ValueError("stale recipe revision; reopen latest version")
    source = catalog.library.load(recipe_id, source_version)
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(source.steps):
        raise ValueError("invalid step index")
    steps = deepcopy(list(source.steps))
    step = steps[index]
    if field in ("voltage_v", "current_a") and step["action"] == "set":
        step["params"][field] = value
    elif field.startswith("until:"):
        predicate = field[6:]
        if predicate not in step["until"]:
            raise ValueError("condition kind mismatch")
        step["until"][predicate] = value
    else:
        raise ValueError("unsupported step field")
    return catalog.next_version(recipe_id, steps)


def insert_step(catalog: RecipeCatalog, recipe_id: str, source_version: int,
                index: int, step: dict):
    """Insert a step and preserve the previous immutable version."""
    latest = catalog.library.versions(recipe_id)
    if not latest or source_version != latest[-1]:
        raise ValueError("stale recipe revision; reopen latest version")
    source = catalog.library.load(recipe_id, source_version)
    if type(index) is not int or not 0 <= index <= len(source.steps):
        raise ValueError("invalid insertion index")
    steps = deepcopy(list(source.steps))
    steps.insert(index, deepcopy(step))
    return catalog.next_version(recipe_id, steps)
