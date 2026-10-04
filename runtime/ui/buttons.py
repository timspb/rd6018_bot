"""Declarative button model for the modular V3 UI."""

from __future__ import annotations

from dataclasses import dataclass

from .actions import UIAction


@dataclass(frozen=True)
class ButtonSpec:
    """A UI capability declaration, not an executable callback."""

    button_id: str
    label: str
    action: UIAction
    requires_confirmation: bool = False
    visible_when: str | None = None
    target_screen: str | None = None
    payload: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.button_id.strip():
            raise ValueError("button_id is required")
        if not self.label.strip():
            raise ValueError("button label is required")
        seen: set[str] = set()
        for key, value in self.payload:
            key = str(key).strip()
            value = str(value)
            if not key:
                raise ValueError("button payload key is required")
            if key in seen:
                raise ValueError(f"duplicate button payload key: {key}")
            seen.add(key)
            if not value:
                raise ValueError(f"button payload value is required: {key}")


__all__ = ["ButtonSpec"]
