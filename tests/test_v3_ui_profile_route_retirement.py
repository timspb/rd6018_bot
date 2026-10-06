from __future__ import annotations

from pathlib import Path
import unittest

from telegram_panel import _is_workspace_callback


ROOT = Path(__file__).resolve().parents[1]


class V3ProfileRouteRetirementTests(unittest.TestCase):
    def test_historical_profile_callbacks_are_not_production_routes(self):
        source = (ROOT / "runtime" / "production_runtime.py").read_text(encoding="utf-8")
        for raw in ("profile_caca", "profile_efb", "profile_agm", "profile_custom"):
            self.assertNotIn(f'F.data == "{raw}"', source)
            self.assertFalse(_is_workspace_callback(raw))

        self.assertNotIn('F.data.in_({"profile_caca", "profile_efb", "profile_agm"})', source)
        self.assertNotIn("async def profile_selection(", source)
        self.assertNotIn("async def custom_mode_start(", source)

    def test_compatibility_charge_menu_emits_only_live_v2_profile_routes(self):
        source = (ROOT / "runtime" / "production_runtime.py").read_text(encoding="utf-8")
        start = source.index("def _build_charge_modes_keyboard()")
        end = source.index("def _build_trend_summary(", start)
        body = source[start:end]

        for callback in ("v2_profile_caca", "v2_profile_efb", "v2_profile_agm", "v2_manual"):
            self.assertIn(f'callback_data="{callback}"', body)
        for callback in ("profile_caca", "profile_efb", "profile_agm", "profile_custom"):
            self.assertNotIn(f'callback_data="{callback}"', body)


if __name__ == "__main__":
    unittest.main()
