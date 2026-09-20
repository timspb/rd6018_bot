import unittest

from telegram.runtime import TelegramRuntime, configure_commands, create_telegram_runtime, run_polling


class TelegramRuntimeAdapterTests(unittest.TestCase):
    def test_factory_owns_single_transport_bundle(self):
        runtime = create_telegram_runtime("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789")

        self.assertIsInstance(runtime, TelegramRuntime)
        self.assertIsNotNone(runtime.bot)
        self.assertIsNotNone(runtime.dispatcher)
        self.assertIsNotNone(runtime.router)
        self.assertIsNot(runtime.bot, runtime.dispatcher)

    def test_factory_rejects_missing_token(self):
        with self.assertRaises(ValueError):
            create_telegram_runtime("")

    def test_polling_helper_registers_shutdown_handler(self):
        runtime = create_telegram_runtime("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789")
        self.assertTrue(callable(run_polling))
        self.assertIsNotNone(runtime.dispatcher.shutdown)

    def test_command_registration_is_owned_by_transport_adapter(self):
        runtime = create_telegram_runtime("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789")
        calls = []

        async def set_my_commands(commands):
            calls.append(commands)

        runtime.bot.set_my_commands = set_my_commands
        import asyncio
        asyncio.run(configure_commands(runtime))

        self.assertEqual([command.command for command in calls[0]], [
            "start", "modes", "off", "logs", "ai", "stats", "help", "entities",
            "v3_approve", "v3_revoke",
        ])

    def test_adapter_has_no_runtime_or_physical_imports(self):
        import ast
        from pathlib import Path

        source = (Path(__file__).parents[1] / "telegram" / "runtime.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        self.assertTrue(imported.isdisjoint({"runtime.physical", "runtime.output", "hass_api"}))


if __name__ == "__main__":
    unittest.main()
