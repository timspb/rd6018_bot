"""Canonical read-only AI analysis screen."""

from __future__ import annotations

from runtime.ui.actions import UIAction
from runtime.ui.buttons import ButtonSpec
from runtime.ui.screen import ScreenId, ScreenSpec


_ANALYSIS_TITLE = "🧠 AI Анализ"


def analysis_button_spec() -> ButtonSpec:
    return ButtonSpec(
        button_id="analysis.open",
        label="🧠 AI анализ",
        action=UIAction.OPEN_ANALYSIS,
        target_screen=ScreenId.ANALYSIS.value,
    )


def build_analysis_screen(rendered_text: str) -> ScreenSpec:
    """Wrap provider-rendered Telegram HTML without duplicating its title."""

    body = str(rendered_text or "").strip()
    prefix = f"<b>{_ANALYSIS_TITLE}</b>"
    if body.startswith(prefix):
        body = body[len(prefix):].lstrip("\n ")
    back = ButtonSpec(
        button_id="analysis.back_home",
        label="⬅ К панели",
        action=UIAction.OPEN_HOME,
        target_screen=ScreenId.HOME.value,
    )
    return ScreenSpec(
        screen_id=ScreenId.ANALYSIS,
        title=_ANALYSIS_TITLE,
        body=body,
        buttons=((back,),),
    )


__all__ = ["analysis_button_spec", "build_analysis_screen"]
