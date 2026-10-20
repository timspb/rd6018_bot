import unittest
import ast
from pathlib import Path
from production_controller import create_production_charge_host


class DummyHass:
    pass


class AutoStrategyScaffoldTests(unittest.IsolatedAsyncioTestCase):
    async def test_presentation_overrides_are_owned_by_application_extensions(self):
        tree = ast.parse(Path("auto_strategy.py").read_text(encoding="utf-8"))
        self.assertFalse(any(isinstance(node, ast.ClassDef) for node in tree.body))
        from application import production_session_extensions as extensions
        for name in ("auto_stage_max_hours", "auto_mix_elapsed_s", "auto_timers",
                     "auto_session_rules_summary", "auto_ai_stage_snapshot",
                     "auto_operator_reason_text"):
            self.assertTrue(callable(getattr(extensions, name)))

    async def test_controller_has_no_stage_router_compatibility_entry(self):
        controller = create_production_charge_host(DummyHass())
        self.assertFalse(hasattr(controller, "_run_stage_scaffold_tick"))

    def test_production_mix_limits_are_20_24_10(self):
        controller = create_production_charge_host(DummyHass())
        for profile, hours in (("Ca/Ca", 20.0), ("EFB", 24.0), ("AGM", 10.0)):
            controller.battery_type = profile
            controller.current_stage = controller.STAGE_MIX
            controller.finish_timer_start = None
            self.assertEqual(controller._get_stage_max_hours(), hours)


if __name__ == "__main__":
    unittest.main()
