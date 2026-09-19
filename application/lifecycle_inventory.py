"""Static lifecycle/import inventory; importing this module has no effects."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LifecycleInventoryEntry:
    module: str
    role: str
    lifecycle_owner: str
    import_side_effects: bool
    globals_or_singletons: bool
    background_workers: bool
    runtime_start: bool
    status: str


_INVENTORY = (
    LifecycleInventoryEntry("bot.py", "production entrypoint", "V2 composition", True, True, True, True, "PRESERVED_V2"),
    LifecycleInventoryEntry("runtime/v2_runtime.py", "legacy runtime", "V2 runtime", True, True, True, True, "COMPATIBILITY_RISK"),
    LifecycleInventoryEntry("bot_legacy.py", "rollback entrypoint", "legacy runtime", False, True, False, True, "ROLLBACK_ONLY"),
    LifecycleInventoryEntry("application/composition_lifecycle.py", "lifecycle contract", "ApplicationComposition", False, False, False, False, "CONTRACT_ONLY"),
    LifecycleInventoryEntry("application/runtime_composition.py", "V3 shadow composition", "ApplicationComposition", False, False, False, False, "SHADOW_ONLY"),
)


def lifecycle_inventory() -> tuple[LifecycleInventoryEntry, ...]:
    return _INVENTORY


__all__ = ["LifecycleInventoryEntry", "lifecycle_inventory"]
