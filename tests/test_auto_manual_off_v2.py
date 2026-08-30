import unittest

from auto_manual_off_v2 import (
    _force_manual_off_inert_for_auto,
    install_auto_manual_off_contract,
)


class FakeController:
    def __init__(self):
        self.calls = []

    async def tick(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return {"ok": True}


class FakeApp:
    def __init__(self):
        self.charge_controller = FakeController()


class AutoManualOffContractTests(unittest.IsolatedAsyncioTestCase):
    def test_keyword_manual_off_is_forced_false(self):
        args, kwargs = _force_manual_off_inert_for_auto(
            (14.7, 1.0, 25.0, True, 12.0, "on"),
            {"manual_off_active": True, "is_cc": False},
        )
        self.assertEqual(args, (14.7, 1.0, 25.0, True, 12.0, "on"))
        self.assertIs(kwargs["manual_off_active"], False)
        self.assertIs(kwargs["is_cc"], False)

    def test_positional_manual_off_is_forced_false_without_duplicate_keyword(self):
        args, kwargs = _force_manual_off_inert_for_auto(
            (14.7, 1.0, 25.0, True, 12.0, "on", True, False),
            {"manual_off_active": True},
        )
        self.assertIs(args[6], False)
        self.assertNotIn("manual_off_active", kwargs)

    async def test_installed_wrapper_preserves_auto_tick_but_removes_manual_off_authority(self):
        app = FakeApp()
        install_auto_manual_off_contract(app)
        result = await app.charge_controller.tick(
            14.7,
            0.6,
            25.0,
            True,
            10.0,
            "on",
            manual_off_active=True,
            is_cc=False,
        )
        self.assertEqual(result, {"ok": True})
        args, kwargs = app.charge_controller.calls[-1]
        self.assertIs(kwargs["manual_off_active"], False)

    async def test_install_is_idempotent(self):
        app = FakeApp()
        install_auto_manual_off_contract(app)
        installed_tick = app.charge_controller.tick
        install_auto_manual_off_contract(app)
        self.assertIs(app.charge_controller.tick, installed_tick)


if __name__ == "__main__":
    unittest.main()
