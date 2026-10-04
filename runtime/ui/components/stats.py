"""Pure operator statistics-location presentation."""

from __future__ import annotations


def render_stats_body() -> str:
    return (
        "Статистика и прогноз заряда теперь в блоке "
        "<b>«Полная инфо»</b> — нажмите кнопку под графиком."
    )


__all__ = ["render_stats_body"]
