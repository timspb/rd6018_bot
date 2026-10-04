"""Canonical static operator-help screen."""

from __future__ import annotations

from runtime.ui.components.help import render_help_body
from runtime.ui.screen import ScreenId, ScreenSpec


def build_help_screen() -> ScreenSpec:
    return ScreenSpec(
        screen_id=ScreenId.HELP,
        title="RD6018: быстрые команды",
        body=render_help_body(),
    )


__all__ = ["build_help_screen"]
