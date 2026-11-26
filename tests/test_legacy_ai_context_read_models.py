import asyncio
import unittest
from unittest.mock import patch

from application.operator_snapshot_provider import build_legacy_ai_context_dict, build_legacy_ai_context_text
from runtime import production_runtime


def _float(value, default=0.0):
    if value is None or value in ("unknown", "unavailable", ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(_live, _key):
    return False


class LegacyAiContextReadModelTests(unittest.TestCase):
    def test_idle_text_is_exact_and_keeps_unknown_capacity(self):
        text = build_legacy_ai_context_text(
            {}, {"is_active": False}, safe_float=_float, canonical_bool=_bool,
            format_snapshot=lambda _snapshot: "SNAPSHOT",
            format_events=lambda _events, limit: f"EVENTS:{limit}",
            strategy_snapshot={"stage": "Idle"}, strategy_events=[],
        )
        self.assertEqual(text, """ПОЛНЫЙ СЛЕПОК RD6018:

Статус выхода: OFF (включен/выключен)
Емкость известна: нет
Емкость АКБ: UNKNOWN Ач

Электрика:
- Напряжение на выходе: 0.000В
- Ток нагрузки: 0.000А
- Мощность: 0.00Вт
- Напряжение на клеммах АКБ: 0.000В

Счетчики:
- Накопленная емкость: 0.000 Ач
- Накопленная энергия: 0.00 Вч

Уставки:
- Целевое напряжение: 0.00В
- Лимит тока: 0.00А
- Защита перенапряжения: 0.0В
- Защита перетока: 0.0А

Статусы:
- Выход включен: нет
- Режим стабилизации напряжения: нет
- Режим стабилизации тока: нет
- Режим измерения АКБ: да

Температура:
- Температура блока: 0.0°C
- Температура АКБ: 0.0°C

Система:
- Входное напряжение БП: 0.0В
- Время работы: неизвестно

Карточка стратегии:
SNAPSHOT""")

    def test_active_text_delegation_preserves_order_and_event_windows(self):
        calls = []

        async def live():
            calls.append("live")
            return {"switch": "on", "voltage": "13.456", "temp_ext": "24"}

        class Controller:
            is_active = True
            current_stage = "Main"
            battery_type = "EFB"
            ah_capacity = 60

            def get_timers(self):
                calls.append("timers")
                return {"total_time": "T", "stage_time": "S", "remaining_time": "R"}

        def recent(limit):
            calls.append(limit)
            return [f"E{limit}"]

        fake_hass = type("H", (), {"get_all_live": staticmethod(live)})()
        with patch.object(production_runtime, "hass", fake_hass), \
                patch.object(production_runtime, "charge_controller", Controller()), \
                patch.object(production_runtime, "get_recent_events", recent), \
                patch.object(production_runtime, "_safe_stage_snapshot", side_effect=lambda _t: {"stage": "Main"}), \
                patch.object(production_runtime, "format_ai_snapshot", side_effect=lambda _s: "CARD"), \
                patch.object(production_runtime, "format_recent_events", side_effect=lambda events, limit: f"IMPORTANT{limit}:{events[0]}"):
            result = asyncio.run(production_runtime.get_ai_context())

        self.assertEqual(calls, ["live", 8, "timers", 5])
        self.assertEqual(result.count("Последние"), 2)
        self.assertIn("- Активный этап: Main\n- Тип АКБ: EFB\n- Заданная емкость: 60Ач\n- Общее время: T\n- Время этапа: S\n- Лимит этапа: R", result)
        self.assertLess(result.index("IMPORTANT8:E8"), result.index("Последние события из лога"))
        self.assertTrue(result.endswith("- E5\n"))

    def test_structured_projection_preserves_active_and_unknown_values(self):
        result = build_legacy_ai_context_dict(
            {"switch": "on", "current": "bad", "battery_voltage": None},
            {"capacity_ah": 60, "stage": "Main", "battery_type": "EFB"},
            {"stage": "Mix", "profile": "AGM", "phase": "CV", "timers": {}},
            safe_float=_float,
        )
        self.assertEqual(result, {
            "output_status": "ON", "current_stage": "Mix", "battery_type": "AGM",
            "mode": "CV", "capacity_ah": 60, "capacity_known": True,
            "remaining_time": "—", "v_batt_now": 0.0, "i_now": 0.0,
            "temp_ext_now": 0.0, "temp_int_now": 0.0,
        })
        fallback = build_legacy_ai_context_dict({}, {"capacity_ah": 0}, {}, safe_float=_float)
        self.assertEqual(fallback["current_stage"], "UNKNOWN")
        self.assertEqual(fallback["capacity_ah"], "UNKNOWN")
        self.assertFalse(fallback["capacity_known"])


if __name__ == "__main__":
    unittest.main()
