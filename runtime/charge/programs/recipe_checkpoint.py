"""Durable recipe progress; restore is read-only and never energizes output."""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import tempfile

from .recipe_engine import StepState
from .recipe_schema import Recipe


@dataclass(frozen=True)
class RecipeCheckpoint:
    recipe_id: str
    version: int
    state: StepState
    output_confirmed_off: bool


def save_checkpoint(path: str | Path, recipe: Recipe, state: StepState, *,
                    output_confirmed_off: bool) -> None:
    """Atomic write of current step; no hardware interaction."""
    if state.recipe_digest != recipe.digest or not 0 <= state.step_index <= len(recipe.steps):
        raise ValueError("checkpoint does not belong to recipe")
    if not math.isfinite(state.entered_at_s) or state.entered_at_s < 0:
        raise ValueError("invalid checkpoint time")
    if type(output_confirmed_off) is not bool:
        raise ValueError("output confirmation must be boolean")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "schema": 1, "recipe_id": recipe.recipe_id, "version": recipe.version,
        "digest": recipe.digest, "step_index": state.step_index,
        "entered_at_s": state.entered_at_s,
        "output_confirmed_off": output_confirmed_off,
    }
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent,
            prefix=".checkpoint-", suffix=".tmp", delete=False
        ) as stream:
            temp_name = stream.name
            json.dump(document, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, destination)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)

def load_checkpoint(path: str | Path, recipe: Recipe) -> RecipeCheckpoint:
    """Validate exact pinned revision. Always require explicit output reconciliation."""
    with Path(path).open(encoding="utf-8") as stream:
        document = json.load(stream)
    if not isinstance(document, dict) or set(document) != {
        "schema", "recipe_id", "version", "digest", "step_index",
        "entered_at_s", "output_confirmed_off",
    }:
        raise ValueError("invalid checkpoint schema")
    if document["schema"] != 1 or document["recipe_id"] != recipe.recipe_id:
        raise ValueError("checkpoint recipe mismatch")
    if type(document["version"]) is not int or document["version"] != recipe.version:
        raise ValueError("checkpoint version mismatch")
    if document["digest"] != recipe.digest:
        raise ValueError("checkpoint content mismatch")
    index = document["step_index"]
    entered = document["entered_at_s"]
    if type(index) is not int or not 0 <= index <= len(recipe.steps):
        raise ValueError("invalid checkpoint index")
    if isinstance(entered, bool) or not isinstance(entered, (int, float)):
        raise ValueError("invalid checkpoint clock")
    if not math.isfinite(entered) or entered < 0:
        raise ValueError("invalid checkpoint clock")
    if type(document["output_confirmed_off"]) is not bool:
        raise ValueError("invalid output confirmation")
    return RecipeCheckpoint(recipe.recipe_id, recipe.version,
                            StepState(recipe.digest, index, float(entered)),
                            document["output_confirmed_off"])
