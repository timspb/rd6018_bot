import unittest

from runtime.ui.components.start_status import (
    format_start_enable_failure,
    format_start_success,
)


class StartStatusTests(unittest.TestCase):
    def test_default_profile_success_uses_prep_wording(self):
        self.assertEqual(
            format_start_success(
                "EFB", 70.0, "recovery", "efb-70",
                battery_voltage_v=11.5,
                initial_threshold_v=12.0,
                prep_skipped=False,
            ),
            "✅ <b>Заряд запущен</b>\n"
            "EFB 70 Ah · Восстановление\n"
            "АКБ: <code>efb-70</code>\n"
            "PREP: мягкий ток до Uакб ≥ 12.0 V.",
        )

    def test_main_entry_preserves_skipped_prep_wording(self):
        self.assertEqual(
            format_start_success(
                "EFB", 70.0, "normal", "efb-70",
                battery_voltage_v=12.0,
                initial_threshold_v=12.0,
                prep_skipped=True,
            ),
            "✅ <b>Заряд запущен</b>\n"
            "EFB 70 Ah · Обычный заряд\n"
            "АКБ: <code>efb-70</code>\n"
            "PREP пропущен: Uакб=12.00 V ≥ 12.0 V.",
        )

    def test_recipe_success_escapes_dynamic_html_and_reports_first_set(self):
        self.assertEqual(
            format_start_success(
                "<EFB>", 70.0, "diagnostic", "bat&1",
                battery_voltage_v=11.5,
                initial_threshold_v=12.0,
                prep_skipped=False,
                recipe_target_voltage_v=13.8,
                recipe_target_current_a=1.2,
            ),
            "✅ <b>Заряд запущен</b>\n"
            "&lt;EFB&gt; 70 Ah · Диагностика\n"
            "АКБ: <code>bat&amp;1</code>\n"
            "Первый SET рецепта: 13.80 В / 1.20 А.",
        )

    def test_confirmed_off_failure_wording_is_unchanged(self):
        self.assertEqual(
            format_start_enable_failure("SafetyViolation", off_confirmed=True),
            "❌ Запуск отменён: ошибка безопасного включения "
            "(SafetyViolation). Выход подтверждён OFF.",
        )


if __name__ == "__main__":
    unittest.main()
