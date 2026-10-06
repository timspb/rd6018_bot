"""Canonical read-only event-journal screen."""

from __future__ import annotations

from runtime.ui.actions import UIAction
from runtime.ui.buttons import ButtonSpec
from runtime.ui.components.journal import render_journal_text
from runtime.ui.models import JournalView
from runtime.ui.screen import ScreenId, ScreenSpec


def journal_button_spec() -> ButtonSpec:
    return ButtonSpec(
        button_id="journal.open",
        label="📋 Лог",
        action=UIAction.OPEN_JOURNAL,
        target_screen=ScreenId.JOURNAL.value,
    )


def build_journal_screen(view: JournalView, *, shown: int = 25) -> ScreenSpec:
    if view.error:
        body = "❌ Ошибка загрузки событий."
    else:
        text = render_journal_text(view.events, shown=shown)
        prefix = "<b>📝 Логи событий</b>\n"
        body = text[len(prefix):].lstrip("\n") if text.startswith(prefix) else text
    back = ButtonSpec(
        button_id="journal.back_home",
        label="⬅ К панели",
        action=UIAction.OPEN_HOME,
        target_screen=ScreenId.HOME.value,
    )
    return ScreenSpec(
        screen_id=ScreenId.JOURNAL,
        title="📝 Логи событий",
        body=body,
        buttons=((back,),),
    )


__all__ = ["build_journal_screen", "journal_button_spec"]
