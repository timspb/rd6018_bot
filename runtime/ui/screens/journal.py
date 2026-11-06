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


def build_journal_screen(view: JournalView, *, offset: int = 0, page_size: int = 4) -> ScreenSpec:
    offset = max(0, int(offset))
    page_size = max(1, min(12, int(page_size)))
    if view.error:
        body = "❌ Ошибка загрузки событий."
    else:
        start = max(0, len(view.events) - offset - page_size)
        end = max(0, len(view.events) - offset)
        page = view.events[start:end]
        text = render_journal_text(page, shown=page_size)
        prefix = "<b>📝 Логи событий</b>\n"
        body = text[len(prefix):].lstrip("\n") if text.startswith(prefix) else text
        if len(view.events) > page_size:
            body = f"<i>События {start + 1}–{end} из {len(view.events)} · новые внизу</i>\n\n{body}"
    rows = []
    if offset + page_size < len(view.events):
        rows.append(ButtonSpec(
            button_id="journal.older", label="⬅ Старее", action=UIAction.OPEN_JOURNAL,
            target_screen=ScreenId.JOURNAL.value,
            payload=(("offset", str(offset + page_size)),),
        ))
    if offset > 0:
        rows.append(ButtonSpec(
            button_id="journal.newer", label="Новее ➡", action=UIAction.OPEN_JOURNAL,
            target_screen=ScreenId.JOURNAL.value,
            payload=(("offset", str(max(0, offset - page_size))),),
        ))
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
        buttons=tuple([[button] for button in rows] + [[back]]),
    )


__all__ = ["build_journal_screen", "journal_button_spec"]
