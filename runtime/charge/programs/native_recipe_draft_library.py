"""Immutable, versioned native-recipe parameter drafts.

This library has no activation API. Existing canonical algorithms and user
SET/OFF recipe storage remain independent. Never overwrite source presets.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from .native_recipe_draft import NativeRecipeDraft, validate_native_draft


def _valid_id(value: str) -> bool:
    return (
        isinstance(value, str) and 1 <= len(value) <= 60
        and all(ch.isascii() and (ch.isalnum() or ch in "-_") for ch in value)
        and not value.startswith("native_")
    )


class NativeRecipeDraftLibrary:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _path(self, name: str, version: int) -> Path:
        if not _valid_id(name):
            raise ValueError("invalid native draft name")
        if type(version) is not int or version < 1:
            raise ValueError("invalid native draft version")
        return self.root / name / f"v{version}.json"

    def versions(self, name: str) -> tuple[int, ...]:
        folder = self._path(name, 1).parent
        return tuple(sorted(int(p.stem[1:]) for p in folder.glob("v[0-9]*.json")
                            if p.stem[1:].isdigit()))

    def list_drafts(self) -> tuple[str, ...]:
        if not self.root.exists():
            return ()
        return tuple(sorted(p.name for p in self.root.iterdir()
                            if p.is_dir() and _valid_id(p.name)
                            and self.versions(p.name)))

    def save(self, name: str, version: int, document: dict) -> NativeRecipeDraft:
        draft = validate_native_draft(document)
        path = self._path(name, version)
        # Immutable source identity: revisions must retain their parent recipe.
        prior_versions = self.versions(name)
        if prior_versions:
            if version != prior_versions[-1] + 1:
                raise ValueError("native draft versions must be sequential")
            previous = self.load(name, prior_versions[-1])
            if draft.base_recipe_id != previous.base_recipe_id:
                raise ValueError("native draft source cannot change")
        elif version != 1:
            raise ValueError("new native draft must start at version 1")
        payload = json.dumps(
            {"name": name, "version": version, "draft": draft.as_document()},
            ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        staged = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", prefix=".native-draft-",
                suffix=".tmp", dir=path.parent, delete=False,
            ) as stream:
                staged = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(staged, path)  # Never replace a published version.
            if os.name == "posix":
                fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        finally:
            if staged is not None:
                staged.unlink(missing_ok=True)
        return draft

    def load(self, name: str, version: int) -> NativeRecipeDraft:
        path = self._path(name, version)
        with path.open(encoding="utf-8") as stream:
            document = json.load(stream)
        if not isinstance(document, dict) or set(document) != {"name", "version", "draft"}:
            raise ValueError("invalid native draft envelope")
        if document["name"] != name or document["version"] != version:
            raise ValueError("native draft identity mismatch")
        return validate_native_draft(document["draft"])
