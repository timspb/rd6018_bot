"""Invoke an existing production stage owner through a native recipe identity.

The profile/intent belong to the accepted controller session. Production
wires this adapter from application.charge_session_tick; it delegates to the
existing run_charge_stage_tick and does not introduce a second stage loop or
authority.
"""
from __future__ import annotations

from typing import Any, Dict

from .native_recipe_catalog import get_native_recipe


def native_recipe_id_for_host(host: Any) -> str | None:
    """Resolve only existing AUTO identities; leave Manual/Custom unchanged."""
    from .native_recipe_catalog import PROFILES, INTENTS
    profile = getattr(host, "battery_type", None)
    intent = getattr(host, "_v2_intent", None)
    value = str(getattr(intent, "value", intent)).lower()
    if profile not in PROFILES or value not in INTENTS:
        return None
    return f"native_{profile.lower().replace('/', '_')}_{value}"


async def run_native_recipe_tick(
    recipe_id: str, host: Any, **stage_inputs: Any
) -> Dict[str, Any]:
    """Run one ordinary production tick for the selected native recipe.

    The existing host owns state, physical effects, and inter-stage transitions.
    """
    description = get_native_recipe(recipe_id)
    intent = getattr(host, "_v2_intent", None)
    intent_value = str(getattr(intent, "value", intent)).lower()
    if host.battery_type != description.profile or intent_value != description.intent:
        raise ValueError("native recipe does not match active profile and intent")
    from application.charge_stage_tick import run_charge_stage_tick
    return await run_charge_stage_tick(host, **stage_inputs)
