from pathlib import Path
import types
import unittest

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import operator_hmi as hmi
from v1_ui_compat import compose_v1_operator_keyboard


class FakeApp:
    def __init__(self):
        self.manual_session_manager = types.SimpleNamespace(is_active=False, state=None)
        self._operator_pause_active = lambda: False
        self.CHART_RANGE_30M = "30m"
        self.CHART_RANGE_2H = "2h"
        self.CHART_RANGE_SESSION = "session"
        self._chart_range_for_user = lambda user_id: self.CHART_RANGE_2H


def state(process, authority, *, output_on=False):
    return types.SimpleNamespace(
        process_state=process,
        authority=authority,
        output_on=output_on,
    )


def callbacks(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def _button(text: str, callback: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback)


def semantic_base(current_state) -> InlineKeyboardMarkup:
    """Minimal upstream V2 semantic surface, independent of global monkey-patching."""
    process = current_state.process_state
    if process is hmi.HmiProcessState.IDLE:
        rows = [
            [_button("⚡ Режимы заряда", "charge_modes")],
            [_button("🔋 АКБ", "v2_batteries")],
            [_button("🔄 Обновить", "operator_refresh")],
        ]
    elif process is hmi.HmiProcessState.RUNNING:
        rows = [
            [
                _button("⏸ Пауза", "operator_pause_toggle"),
                _button("🛑 Стоп", "operator_managed_stop"),
            ],
            [_button("ℹ Подробнее", "operator_details"), _button("📋 События", "logs")],
            [_button("🔄 Обновить", "operator_refresh")],
        ]
    elif process is hmi.HmiProcessState.CONTAINMENT:
        rows = [
            [_button("ℹ Подробнее", "operator_details"), _button("📋 События", "logs")],
            [_button("🔋 АКБ", "v2_batteries")],
            [_button("🔄 Обновить", "operator_refresh")],
        ]
    elif process is hmi.HmiProcessState.HANDS_OFF:
        rows = [
            [_button("🧲 Подхватить текущий Mix", "rd_live_mix")],
            [_button("⏹ Output OFF", "rd_hands_off_output_off")],
            [_button("ℹ Подробнее", "operator_details"), _button("📋 События", "logs")],
            [_button("🔄 Обновить", "operator_refresh")],
        ]
    elif process is hmi.HmiProcessState.ADOPTED_MIX:
        rows = [
            [_button("⏹ Остановить Mix", "operator_adopted_stop")],
            [_button("ℹ Подробнее", "operator_details"), _button("📋 События", "logs")],
            [_button("🔄 Обновить", "operator_refresh")],
        ]
    elif process is hmi.HmiProcessState.STORAGE:
        rows = [
            [_button("ℹ Подробнее", "operator_details"), _button("📋 События", "logs")],
            [_button("🔄 Обновить", "operator_refresh")],
        ]
    else:
        rows = [[_button("🔄 Обновить", "operator_refresh")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


class V1UiCompatibilityTests(unittest.TestCase):
    def compose(self, current_state):
        app = FakeApp()
        base = semantic_base(current_state)
        return app, compose_v1_operator_keyboard(app, current_state, base, hmi)

    def test_idle_restores_v1_primary_shell_with_v2_safe_start(self):
        app, markup = self.compose(
            state(hmi.HmiProcessState.IDLE, hmi.HmiAuthority.NONE, output_on=False)
        )
        del app
        rows = [[button.text for button in row] for row in markup.inline_keyboard]
        cb = callbacks(markup)

        self.assertEqual(rows[0], ["🔄 Обновить", "📋 Полная инфо"])
        self.assertEqual(rows[1], ["📝 Логи", "🧠 AI анализ"])
        self.assertEqual(rows[2], ["🚀 СТАРТ", "⚙️ Режимы"])
        self.assertEqual(rows[3], ["🛠 Ещё"])
        self.assertIn("operator_refresh", cb)
        self.assertIn("operator_details", cb)
        self.assertIn("logs", cb)
        self.assertIn("ai_analysis", cb)
        self.assertIn("v2_batteries", cb)
        self.assertIn("charge_modes", cb)
        self.assertIn("operator_more", cb)
        self.assertNotIn("power_toggle", cb)

    def test_filtered_idle_does_not_reconstruct_start_or_more(self):
        current_state = state(
            hmi.HmiProcessState.IDLE,
            hmi.HmiAuthority.NONE,
            output_on=False,
        )
        base = InlineKeyboardMarkup(
            inline_keyboard=[
                [_button("⚡ Режимы заряда", "charge_modes")],
                [_button("🔄 Обновить", "operator_refresh")],
            ]
        )
        markup = compose_v1_operator_keyboard(FakeApp(), current_state, base, hmi)
        cb = callbacks(markup)

        self.assertIn("operator_refresh", cb)
        self.assertIn("operator_details", cb)
        self.assertIn("logs", cb)
        self.assertIn("ai_analysis", cb)
        self.assertNotIn("v2_batteries", cb)
        self.assertNotIn("charge_modes", cb)
        self.assertNotIn("operator_more", cb)
        self.assertNotIn("power_toggle", cb)

    def test_running_keeps_v2_pause_stop_and_restores_v1_information_rows(self):
        _app, markup = self.compose(
            state(hmi.HmiProcessState.RUNNING, hmi.HmiAuthority.AUTO, output_on=True)
        )
        rows = [[button.text for button in row] for row in markup.inline_keyboard]
        cb = callbacks(markup)

        self.assertEqual(rows[0], ["⏸ Пауза", "🛑 Стоп"])
        self.assertIn(["🔄 Обновить", "📋 Полная инфо"], rows)
        self.assertIn(["📝 Логи", "🧠 AI анализ"], rows)
        self.assertIn(["🛠 Ещё"], rows)
        self.assertIn("operator_pause_toggle", cb)
        self.assertIn("operator_managed_stop", cb)
        self.assertNotIn("power_toggle", cb)
        self.assertNotIn("v2_batteries", cb)
        self.assertNotIn("charge_modes", cb)

    def test_containment_never_becomes_a_start_surface(self):
        _app, markup = self.compose(
            state(hmi.HmiProcessState.CONTAINMENT, hmi.HmiAuthority.CONTAINMENT)
        )
        cb = callbacks(markup)

        self.assertIn("operator_refresh", cb)
        self.assertIn("operator_details", cb)
        self.assertIn("logs", cb)
        self.assertIn("ai_analysis", cb)
        self.assertNotIn("v2_batteries", cb)
        self.assertNotIn("charge_modes", cb)
        self.assertNotIn("power_toggle", cb)
        self.assertNotIn("operator_more", cb)

    def test_hands_off_keeps_ownership_actions_but_never_adds_start(self):
        _app, markup = self.compose(
            state(hmi.HmiProcessState.HANDS_OFF, hmi.HmiAuthority.EXTERNAL, output_on=True)
        )
        cb = callbacks(markup)

        self.assertIn("rd_live_mix", cb)
        self.assertIn("rd_hands_off_output_off", cb)
        self.assertIn("operator_refresh", cb)
        self.assertIn("operator_details", cb)
        self.assertIn("logs", cb)
        self.assertIn("ai_analysis", cb)
        self.assertNotIn("v2_batteries", cb)
        self.assertNotIn("charge_modes", cb)
        self.assertNotIn("operator_more", cb)

    def test_adopted_mix_keeps_stop_first_and_only_adds_read_only_v1_rows(self):
        _app, markup = self.compose(
            state(hmi.HmiProcessState.ADOPTED_MIX, hmi.HmiAuthority.ADOPTED_MIX, output_on=True)
        )
        rows = [[button.text for button in row] for row in markup.inline_keyboard]
        cb = callbacks(markup)

        self.assertEqual(rows[0], ["⏹ Остановить Mix"])
        self.assertIn("operator_adopted_stop", cb)
        self.assertIn("ai_analysis", cb)
        self.assertNotIn("v2_batteries", cb)
        self.assertNotIn("charge_modes", cb)
        self.assertNotIn("operator_more", cb)

    def test_storage_remains_terminal_but_keeps_v1_information_and_v2_service(self):
        _app, markup = self.compose(
            state(hmi.HmiProcessState.STORAGE, hmi.HmiAuthority.AUTO, output_on=False)
        )
        cb = callbacks(markup)

        self.assertIn("operator_refresh", cb)
        self.assertIn("operator_details", cb)
        self.assertIn("logs", cb)
        self.assertIn("ai_analysis", cb)
        self.assertIn("operator_more", cb)
        self.assertNotIn("power_toggle", cb)
        self.assertNotIn("charge_modes", cb)
        self.assertNotIn("v2_batteries", cb)

    def test_chart_ranges_are_not_duplicated_by_compatibility_shell(self):
        app, markup = self.compose(
            state(hmi.HmiProcessState.IDLE, hmi.HmiAuthority.NONE, output_on=False)
        )
        self.assertFalse(any(str(cb).startswith("operator_graph_") for cb in callbacks(markup)))

        graph = hmi._graph_keyboard(app, 1)
        graph_callbacks = callbacks(graph)
        self.assertEqual(
            graph_callbacks[:3],
            ["operator_graph_30m", "operator_graph_2h", "operator_graph_session"],
        )

    def test_production_composes_v1_shell_before_truth_and_autonomous_filters(self):
        truth = Path("operator_output_truth.py").read_text(encoding="utf-8")
        self.assertIn("install_v1_ui_compat(app)", truth)
        self.assertLess(
            truth.index("install_v1_ui_compat(app)"),
            truth.index("original_keyboard_builder = hmi.build_operator_keyboard"),
        )

        bot = Path("bot.py").read_text(encoding="utf-8")
        self.assertLess(
            bot.index("install_operator_output_truth(_legacy)"),
            bot.index("install_rd_autonomous_final_hmi(_legacy"),
        )


if __name__ == "__main__":
    unittest.main()
