"""Snapshot a versioned native recipe for one AUTO charging session.

Read-only selection. This does not apply dynamic settings to stage owners or
authorize START. Snapshot values are immutable across later library edits.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any

from .native_recipe_catalog import get_native_recipe
from .native_recipe_draft import NativeRecipeDraft, validate_native_draft
from .native_recipe_draft_library import NativeRecipeDraftLibrary


@dataclass(frozen=True)
class NativeRecipeSessionSelection:
    name: str
    version: int
    base_recipe_id: str
    profile: str
    intent: str
    overrides: tuple[tuple[str, float | int], ...]
    content_sha256: str

    def to_document(self) -> dict:
        return {"name": self.name, "version": self.version,
                "base_recipe_id": self.base_recipe_id, "profile": self.profile,
                "intent": self.intent, "overrides": dict(self.overrides),
                "content_sha256": self.content_sha256}

    def _payload(self) -> dict:
        return {"base_recipe_id": self.base_recipe_id,
                "name": self.name, "version": self.version,
                "overrides": dict(self.overrides)}

    @staticmethod
    def from_document(document: dict) -> "NativeRecipeSessionSelection":
        if not isinstance(document, dict) or set(document) != {
            "name", "version", "base_recipe_id", "profile", "intent",
            "overrides", "content_sha256",
        }:
            raise ValueError("invalid pinned native recipe session")
        if (not isinstance(document["name"], str)
                or type(document["version"]) is not int
                or document["version"] < 1):
            raise ValueError("invalid pinned native recipe identity")
        draft = validate_native_draft({
            "schema": 1, "execution_kind": "native_authority",
            "base_recipe_id": document["base_recipe_id"],
            "overrides": document["overrides"],
        })
        entry = get_native_recipe(draft.base_recipe_id)
        if entry.profile != document["profile"] or entry.intent != document["intent"]:
            raise ValueError("native recipe profile/intent mismatch")
        selection = NativeRecipeSessionSelection(
            name=document["name"], version=document["version"],
            base_recipe_id=entry.recipe_id, profile=entry.profile,
            intent=entry.intent, overrides=draft.overrides,
            content_sha256=document["content_sha256"],
        )
        if selection.content_sha256 != _digest(selection._payload()):
            raise ValueError("native recipe pinned content was changed")
        return selection


def _digest(payload: dict) -> str:
    return sha256(json.dumps(payload, sort_keys=True, allow_nan=False,
                             separators=(",", ":")).encode("utf-8")).hexdigest()


def select_native_recipe_version(
    library: NativeRecipeDraftLibrary,
    name: str, version: int, *, profile: str, intent: Any,
) -> NativeRecipeSessionSelection:
    draft: NativeRecipeDraft = library.load(name, version)
    entry = get_native_recipe(draft.base_recipe_id)
    intent_name = str(getattr(intent, "value", intent)).lower()
    if profile != entry.profile or intent_name != entry.intent:
        raise ValueError("selected recipe does not match requested charge profile/intent")
    payload = {"name": name, "version": version,
               "base_recipe_id": entry.recipe_id,
               "overrides": dict(draft.overrides)}
    return NativeRecipeSessionSelection(
        name=name, version=version, base_recipe_id=entry.recipe_id,
        profile=entry.profile, intent=entry.intent, overrides=draft.overrides,
        content_sha256=_digest(payload),
    )
