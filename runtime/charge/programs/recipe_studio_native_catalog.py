"""Read-only metadata snapshot for the existing native recipe UI."""
from __future__ import annotations

from runtime.charge.programs.native_recipe_catalog import native_recipes
from runtime.charge.programs.native_recipe_parameters import native_recipe_parameters
from runtime.charge.programs.native_recipe_draft import validate_native_draft
from runtime.charge.programs.native_recipe_session import require_supported_native_execution
from runtime.config.variable_spec import OverridePolicy


def native_studio_catalog() -> dict:
    """Discover editable settings from their actual owners, not UI constants."""
    result = []
    for entry in native_recipes():
        fields = []
        for spec in native_recipe_parameters(entry.recipe_id):
            policy_editable = spec.override_policy == OverridePolicy.CONFIG_FILE
            supported = False
            if policy_editable:
                try:
                    draft = validate_native_draft({
                        "schema": 1, "base_recipe_id": entry.recipe_id,
                        "execution_kind": "native_authority",
                        "overrides": {spec.key: spec.default},
                    })
                    require_supported_native_execution(draft)
                    supported = True
                except ValueError:
                    pass
            fields.append({
                "key": spec.key, "description": spec.description,
                "unit": spec.unit, "default": spec.default,
                "type": spec.value_type.__name__,
                "minimum": spec.minimum, "maximum": spec.maximum,
                "editable": policy_editable and supported,
                "owner": spec.owner, "change_effect": spec.change_effect.value,
            })
        result.append({
            "recipe_id": entry.recipe_id, "profile": entry.profile,
            "intent": entry.intent, "parameters": fields,
        })
    return {"schema": "rd6018.native_recipe_ui_catalog.v1", "recipes": result}
