"""Pure, versioned user charge recipes; no hardware execution or global settings."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Any, Mapping

CONDITIONS = frozenset({"voltage_gte", "voltage_lte", "current_gte",
                        "current_lte", "temperature_gte", "temperature_lte"})
ACTIONS = frozenset({"set", "off", "wait"})
MAX_STEPS = 128


@dataclass(frozen=True)
class Recipe:
    recipe_id: str
    version: int
    steps: tuple[dict[str, Any], ...]
    digest: str


def _number(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label}: finite number required")
    n = float(value)
    if not math.isfinite(n) or (positive and n <= 0):
        raise ValueError(f"{label}: invalid number")
    return n

def parse_recipe(document: Mapping[str, Any], *,
                 max_voltage_v: float, max_current_a: float) -> Recipe:
    """Validate structure and hardware ceilings; never execute the recipe."""
    if not isinstance(document, Mapping):
        raise ValueError("recipe must be a mapping")
    recipe_id = document.get("id")
    version = document.get("version")
    steps = document.get("steps")
    if not isinstance(recipe_id, str) or not recipe_id or len(recipe_id) > 80:
        raise ValueError("invalid recipe id")
    if not all(c.isascii() and (c.isalnum() or c in "-_") for c in recipe_id):
        raise ValueError("recipe id must be ASCII alphanumeric/dash/underscore")
    if type(version) is not int or version < 1:
        raise ValueError("invalid recipe version")
    if not isinstance(steps, list) or not (1 <= len(steps) <= MAX_STEPS):
        raise ValueError("invalid recipe steps")
    ceiling_v = _number(max_voltage_v, "voltage ceiling", positive=True)
    ceiling_i = _number(max_current_a, "current ceiling", positive=True)
    normalized = []
    for index, raw in enumerate(steps):
        if not isinstance(raw, Mapping) or set(raw) != {"action", "params", "until"}:
            raise ValueError(f"step {index}: expected action, params and until")
        action, params, until = raw["action"], raw["params"], raw["until"]
        if action not in ACTIONS or not isinstance(params, Mapping):
            raise ValueError(f"step {index}: invalid action")
        if action == "set":
            if set(params) != {"voltage_v", "current_a"}:
                raise ValueError(f"step {index}: set requires voltage_v,current_a")
            v = _number(params["voltage_v"], "voltage", positive=True)
            i = _number(params["current_a"], "current", positive=True)
            if v > ceiling_v or i > ceiling_i:
                raise ValueError(f"step {index}: hardware ceiling exceeded")
            clean_params = {"voltage_v": v, "current_a": i}
        elif action == "wait":
            if params:
                raise ValueError(f"step {index}: wait must not set hardware")
            clean_params = {}
        else:
            if params:
                raise ValueError(f"step {index}: off must not set hardware")
            clean_params = {}
        if not isinstance(until, Mapping) or len(until) != 1:
            raise ValueError(f"step {index}: one transition condition required")
        predicate, value = next(iter(until.items()))
        if predicate != "after_seconds" and predicate not in CONDITIONS:
            raise ValueError(f"step {index}: unsupported condition")
        threshold = _number(value, predicate, positive=predicate == "after_seconds")
        normalized.append({"action": action, "params": clean_params,
                           "until": {predicate: threshold}})
    canonical = {"id": recipe_id, "version": version, "steps": normalized}
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return Recipe(recipe_id, version, tuple(normalized),
                  sha256(payload.encode("utf-8")).hexdigest())
