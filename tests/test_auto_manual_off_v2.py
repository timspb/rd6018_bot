import unittest


class AutoManualOffContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_production_controller_owns_manual_off_inertness_without_installer(self):
        from charge_controller_v2 import ChargeControllerV2

        controller = ChargeControllerV2(object())
        controller.start("EFB", 70)
        captured = {}

        async def scaffold(**kwargs):
            captured.update(kwargs)
            controller.last_update_time = 1000.0
            return {}

        controller._run_stage_scaffold_tick = scaffold
        controller._new_runtime = lambda **_: type(
            "Runtime",
            (),
            {"observe": lambda self, point: type("Record", (), {"events": (), "decision": None})()},
        )()

        await controller.tick(
            14.8,
            1.0,
            25.0,
            True,
            1.0,
            "on",
            manual_off_active=True,
            is_cc=False,
        )
        self.assertIs(captured["manual_off_active"], False)

    def test_production_composition_has_no_manual_off_compatibility_edge(self):
        from pathlib import Path

        source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
        self.assertNotIn("install_auto_manual_off_contract", source)
        self.assertNotIn("auto_manual_off_v2", source)


if __name__ == "__main__":
    unittest.main()
