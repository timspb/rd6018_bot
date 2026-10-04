"""Canonical static statistics-location screen."""

from __future__ import annotations

from runtime.ui.components.stats import render_stats_body
from runtime.ui.screen import ScreenId, ScreenSpec


def build_stats_screen() -> ScreenSpec:
    return ScreenSpec(
        screen_id=ScreenId.STATS,
        title="📋 Статистика",
        body=render_stats_body(),
    )


__all__ = ["build_stats_screen"]
