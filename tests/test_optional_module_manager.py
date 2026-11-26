"""Source/fake acceptance for restart-scoped optional modules and physical AI removal."""
from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from runtime.optional_modules import (
    ModuleManager, ModuleSpec, configured_enabled, optional_export,
)

ROOT = Path(__file__).resolve().parents[1]
INERT_ENV = {
    "TG_TOKEN": "123456:INERT_LOCAL_TEST_ONLY",
    "HA_URL": "http://127.0.0.1:8123",
    "HA_TOKEN": "INERT_LOCAL_TEST_ONLY",
    "PYTHONDONTWRITEBYTECODE": "1",
}


class OptionalModuleManagerTests(unittest.TestCase):
    def test_disabled_module_does_not_import_ai(self):
        with patch.dict(os.environ, {"RD6018_MODULE_AI": "0"}):
            manager = ModuleManager()
            self.assertEqual(manager.status("ai"), "disabled")
            self.assertIsNone(optional_export("integrations.ai.engine", "ask_deepseek"))
            self.assertFalse(manager.install("ai", SimpleNamespace()))
            self.assertFalse(manager.installed("ai"))
            with self.assertRaises(KeyError):
                manager.status("safety")

    def test_removed_optional_ai_uses_neutral_operator_snapshot_without_alarm(self):
        from application.operator_snapshot_provider import build_safe_stage_snapshot
        from runtime.optional_modules import ModuleUnavailable

        class Controller:
            is_active = True
            current_stage = "Main"
            battery_type = "Ca/Ca"
            previous_stage = "Prep"

            def get_ai_stage_snapshot(self, temp_c=None):
                raise ModuleUnavailable("AI removed")

            def get_timers(self):
                return {"remaining_time": "12:34"}

            def _get_target_v_i(self, temp_c=None):
                return 14.4, 4.0

        errors = []
        result = build_safe_stage_snapshot(Controller(), 24.0, on_error=errors.append)
        self.assertEqual(errors, [])
        self.assertEqual(result["stage"], "Main")
        self.assertEqual(result["target_voltage"], 14.4)
        self.assertEqual(result["target_current"], 4.0)

    def test_read_only_status_command(self):
        env = dict(os.environ, **INERT_ENV, RD6018_MODULE_AI="0")
        result = subprocess.run(
            [sys.executable, "-m", "runtime.optional_modules", "status"],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), '{"ai": "disabled"}')

    def test_invalid_setting_fails_instead_of_silently_enabling(self):
        with patch.dict(os.environ, {"RD6018_MODULE_AI": "wrong"}):
            with self.assertRaises(ValueError):
                configured_enabled("ai")

    def test_disabled_ai_hides_hmi_button_help_and_telegram_command(self):
        from runtime.ui.components.hmi_navigation_keyboards import _more_keyboard
        from runtime.ui.components.hmi_state import HmiProcessState
        from runtime.ui.components.help import render_help_body
        from telegram.runtime import configure_commands

        class Bot:
            def __init__(self):
                self.commands = []

            async def set_my_commands(self, commands):
                self.commands = commands

        with patch.dict(os.environ, {"RD6018_MODULE_AI": "0"}):
            state = SimpleNamespace(process_state=HmiProcessState.IDLE, output_on=False)
            markup = _more_keyboard(state, SimpleNamespace())
            callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
            self.assertNotIn("ui:nav.analysis", callbacks)
            self.assertNotIn("/ai", render_help_body())
            telegram = SimpleNamespace(bot=Bot())
            asyncio.run(configure_commands(telegram))
            self.assertNotIn("ai", {cmd.command for cmd in telegram.bot.commands})

    def test_installer_runs_once_and_shutdown_is_reverse_lifecycle(self):
        calls = []
        fake = SimpleNamespace(
            install=lambda app: calls.append(("install", app)),
            shutdown=lambda app: calls.append(("stop", app)),
        )
        spec = ModuleSpec("test", "example.test", "example.test.module")
        manager = ModuleManager((spec,))
        app = object()
        with patch("runtime.optional_modules.package_present", return_value=True), \
             patch("runtime.optional_modules.importlib.import_module", return_value=fake):
            self.assertTrue(manager.install("test", app))
            self.assertTrue(manager.install("test", app))
        self.assertEqual(calls, [("install", app)])
        self.assertTrue(manager.installed("test"))
        asyncio.run(manager.shutdown(app))
        self.assertFalse(manager.installed("test"))
        self.assertEqual(calls[-1], ("stop", app))

    @staticmethod
    def _run_shadow(*, remove_ai: bool, disabled: bool) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory(prefix="rd6018-optional-ai-") as folder:
            shadow = Path(folder)
            def mirror(item: Path, target: Path) -> None:
                # GitHub Windows runners may forbid symlinks. A copied offline
                # test tree must be equally valid and never touch original bytes.
                try:
                    target.symlink_to(item, target_is_directory=item.is_dir())
                except OSError:
                    if item.is_dir():
                        shutil.copytree(item, target, ignore=shutil.ignore_patterns(
                            "__pycache__", ".git", ".venv", "venv", "tests", "*.pyc"))
                    else:
                        shutil.copy2(item, target)

            for item in ROOT.iterdir():
                if item.name == "integrations":
                    target = shadow / "integrations"
                    target.mkdir()
                    for sub in item.iterdir():
                        if remove_ai and sub.name == "ai":
                            continue
                        mirror(sub, target / sub.name)
                elif item.is_dir():
                    if item.name in {".git", "tests", "__pycache__", ".recipe-studio-local", ".venv", "venv",
                                     "docs", "reports", "state"}:
                        continue
                    mirror(item, shadow / item.name)
                elif item.is_file() and item.suffix == ".py":
                    mirror(item, shadow / item.name)

            script = """
import asyncio, importlib.util, sys
from runtime.optional_modules import ModuleManager
if {remove}:
    assert importlib.util.find_spec("integrations.ai") is None
import bot
assert bot._composition.composed
assert bot._composition.modules.status("ai") == "{expected}"
assert bot._composition.modules.installed("ai") is {installed}
if not {installed}:
    assert not getattr(bot._composition.runtime, "_v3_analysis_screen_installed", False)
    assert "integrations.ai" not in sys.modules
    from charge_controller import ManagedChargeController
    from runtime.optional_modules import ModuleUnavailable
    try:
        ManagedChargeController.__new__(ManagedChargeController).get_ai_stage_snapshot()
    except ModuleUnavailable:
        pass
    else:
        raise AssertionError("optional AI projection was not disabled")
    from runtime import production_runtime
    from runtime.ui.components.hmi_navigation_keyboards import _more_keyboard
    from runtime.ui.components.hmi_state import HmiProcessState
    from runtime.ui.components.help import render_help_body
    from types import SimpleNamespace
    state=SimpleNamespace(process_state=HmiProcessState.IDLE, output_on=False)
    markup=_more_keyboard(state, production_runtime)
    assert all(btn.callback_data != "ui:nav.analysis"
               for row in markup.inline_keyboard for btn in row)
    assert "/ai" not in render_help_body()
    assert asyncio.run(production_runtime.get_ai_context()) == ""
    assert asyncio.run(production_runtime.get_ai_context_dict()) == {{}}
    assert asyncio.run(production_runtime._build_ai_analysis_text()) == "AI-модуль отключён."
print("OPTIONAL_AI_BOOTSTRAP_PASS")
""".format(
                remove=remove_ai,
                expected="missing" if remove_ai and not disabled else ("disabled" if disabled else "installed"),
                installed=not (remove_ai or disabled),
            )
            env = dict(os.environ, **INERT_ENV, PYTHONPATH=str(shadow))
            if disabled:
                env["RD6018_MODULE_AI"] = "0"
            else:
                env.pop("RD6018_MODULE_AI", None)
            return subprocess.run(
                [sys.executable, "-c", script], cwd=shadow, env=env,
                capture_output=True, text=True, timeout=45,
            )

    def test_ai_enabled_registers_once(self):
        result = self._run_shadow(remove_ai=False, disabled=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OPTIONAL_AI_BOOTSTRAP_PASS", result.stdout)

    def test_ai_disabled_bootstraps_without_importing_package(self):
        result = self._run_shadow(remove_ai=False, disabled=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_physically_removed_ai_package_does_not_break_core_composition(self):
        # The namespace 'integrations' exists in the isolated copy, but
        # 'integrations/ai' is physically absent, not just mocked unavailable.
        result = self._run_shadow(remove_ai=True, disabled=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
