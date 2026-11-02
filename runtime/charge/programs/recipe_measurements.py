"""Append-only measurements for a pinned experimental run, no hardware access."""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
from typing import Mapping
from .recipe_schema import Recipe

FIELDS = frozenset({"voltage", "current", "temperature"})

def record_measurement(path: str | Path, *, recipe: Recipe, session_id: str,
                       timestamp_s: float, values: Mapping[str, float]) -> None:
    if not session_id or isinstance(timestamp_s, bool) or not math.isfinite(float(timestamp_s)):
        raise ValueError("invalid measurement identity or time")
    if not values or not set(values).issubset(FIELDS):
        raise ValueError("unknown or empty measurements")
    clean = {}
    for key, raw in values.items():
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
            raise ValueError("non-finite or invalid measurement")
        clean[key] = float(raw)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    item = {"session": session_id, "recipe": recipe.recipe_id,
            "version": recipe.version, "digest": recipe.digest,
            "timestamp_s": float(timestamp_s), "measurements": clean}
    with target.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(item, sort_keys=True, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
