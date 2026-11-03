import unittest
from aiogram.types import InlineKeyboardButton

from runtime.ui.telegram.recipe_buttons import editor_page


class EditorPaginationTests(unittest.TestCase):
    def test_later_steps_and_append_controls_remain_reachable(self):
        rows = [[InlineKeyboardButton(text=f"Шаг {i}", callback_data=f"recipes:step:test:1:{i}:delete")]
                for i in range(85)]
        rows.extend([
            [InlineKeyboardButton(text="Добавить SET", callback_data="recipes:append:test:1:set")],
            [InlineKeyboardButton(text="Добавить OFF", callback_data="recipes:append:test:1:off")],
            [InlineKeyboardButton(text="Добавить WAIT", callback_data="recipes:append:test:1:wait")],
        ])
        first = editor_page(rows, name="test", version=1, page=0)
        last = editor_page(rows, name="test", version=1, page=2)
        first_buttons = [b for row in first.inline_keyboard for b in row]
        last_buttons = [b for row in last.inline_keyboard for b in row]
        self.assertTrue(any(b.callback_data == "recipes:edit:test:1:1" for b in first_buttons))
        self.assertTrue(any(b.callback_data == "recipes:edit:test:1:1" for b in last_buttons))
        self.assertTrue(any(b.callback_data == "recipes:append:test:1:wait" for b in last_buttons))
        self.assertTrue(any(b.callback_data == "recipes:view:test:1" for b in last_buttons))
        self.assertLessEqual(len(last_buttons), 33)
        self.assertTrue(all(len(b.callback_data.encode("utf-8")) <= 64 for b in last_buttons))

    def test_invalid_page_not_silently_clamped(self):
        rows = [[InlineKeyboardButton(text="x", callback_data="x")]]
        with self.assertRaises(ValueError):
            editor_page(rows, name="test", version=1, page=1)
