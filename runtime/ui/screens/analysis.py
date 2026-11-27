"""Compatibility exports for the optional AI analysis presentation."""
from __future__ import annotations

from runtime.ui.buttons import ButtonSpec
from runtime.ui.screen import ScreenSpec


def analysis_button_spec() -> ButtonSpec:
    from integrations.ai.screen import analysis_button_spec as build
    return build()


def build_analysis_screen(rendered_text: str) -> ScreenSpec:
    from integrations.ai.screen import build_analysis_screen as build
    return build(rendered_text)


__all__ = ["analysis_button_spec", "build_analysis_screen"]
