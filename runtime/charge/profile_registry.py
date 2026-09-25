"""Pure charge profile registry for the Phase 7 domain runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from .battery import BatteryProfile
from .chemistry import ChemistryProfile, ProductionChemistry
from .profiles.recipe import ValidatedChargeRecipe, factory_recipe
from .strategy import ChargeRecipe


@dataclass(frozen=True)
class ProfileDefinition:
    name: str
    chemistry: ChemistryProfile
    recipe: ChargeRecipe
    source: str = "factory"


ProfileFactory = Callable[[], ValidatedChargeRecipe]


class ProfileRegistry:
    """Own profile definitions; never loads transport or persistence state."""

    def __init__(self, definitions: Mapping[str, ProfileDefinition] | None = None) -> None:
        self._definitions = {str(k).lower(): v for k, v in (definitions or {}).items()}

    @classmethod
    def with_defaults(cls) -> "ProfileRegistry":
        registry = cls()
        for label in ("AGM", "EFB", "CA_CA"):
            validated = factory_recipe(label)
            registry.register(ProfileDefinition(label, validated.chemistry, validated.recipe))
        return registry

    def register(self, definition: ProfileDefinition) -> None:
        key = definition.name.strip().lower()
        if not key or key in self._definitions:
            raise ValueError(f"invalid or duplicate profile: {definition.name}")
        self._definitions[key] = definition

    def register_custom(self, name: str, recipe: ChargeRecipe, *, chemistry: ChemistryProfile = ChemistryProfile.CALCIUM) -> None:
        self.register(ProfileDefinition(name, chemistry, recipe, source="custom"))

    def available(self) -> tuple[str, ...]:
        return tuple(sorted(self._definitions))

    def get(self, name: str) -> ProfileDefinition:
        key = str(name).strip().lower()
        try:
            return self._definitions[key]
        except KeyError as exc:
            raise KeyError(f"unknown charge profile: {key}") from exc

    def create_battery(self, name: str, capacity_ah: float, *, manufacturer: str | None = None) -> BatteryProfile:
        definition = self.get(name)
        return BatteryProfile(definition.chemistry, capacity_ah, manufacturer=manufacturer, recipe=definition.recipe)
