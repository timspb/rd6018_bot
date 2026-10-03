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

    def __post_init__(self) -> None:
        if not self.button_id.strip():
            raise ValueError("button_id is required")
        if not self.label.strip():
            raise ValueError("button label is required")


__all__ = ["ButtonSpec"]
