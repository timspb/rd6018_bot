"""Canonical read-only RD6018 entity-status screen."""

from __future__ import annotations

from runtime.ui.actions import UIAction
from runtime.ui.buttons import ButtonSpec
from runtime.ui.components.entities import render_entities_body
from runtime.ui.models import EntityStatusView
from runtime.ui.screen import ScreenId, ScreenSpec


def build_entities_screen(view: EntityStatusView) -> ScreenSpec:
    back = ButtonSpec(
        button_id="entities.back_home",
        label="⬅ К панели",
        action=UIAction.OPEN_HOME,
        target_screen=ScreenId.HOME.value,
    )
    return ScreenSpec(
        screen_id=ScreenId.ENTITIES,
        title="📡 Статус сущностей RD6018",
        body=render_entities_body(view),
        buttons=((back,),),
    )


__all__ = ["build_entities_screen"]
