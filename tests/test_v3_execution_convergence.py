from __future__ import annotations

import ast
import asyncio
import inspect
from pathlib import Path
from types import SimpleNamespace
import unittest

from application.execution_intent.models import ExecutionIntent, SafetyContext
from application.execution_port import ExecutionPort, get_or_create_execution_port


ROOT = Path(__file__).resolve().parents[1]


class _Owner:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.live = {
            "switch": "on",
            "output_state_code_v2": 1,
            "battery_voltage": 13.0,
            "set_voltage_readback_v2": 14.4,
            "set_current_readback_v2": 2.0,
        }

    async def get_all_live(self):
        return dict(self.live)

    async def turn_off(self):
        self.calls.append(("turn_off",))
        self.live["output_state_code_v2"] = 0
        return True


def _intent(mode: str = "TEST_OFF") -> ExecutionIntent:
    return ExecutionIntent(
        requested_voltage_v=0.0,
        requested_current_a=0.0,
        requested_mode=mode,
        source_decision_id="decision:test",
        safety_context=SafetyContext(
            telemetry_state="FRESH",
            lease_state="V2_PHYSICAL_OWNER",
            verification_state="REQUIRED",
            limits_reference="test",
        ),
    )


class V3ExecutionConvergenceTests(unittest.TestCase):
    def test_application_scoped_execution_port_is_singleton_per_app(self):
        app = SimpleNamespace(hass=_Owner())
        first = get_or_create_execution_port(app)
        second = get_or_create_execution_port(app)
        self.assertIs(first, second)
        self.assertIs(app.execution_port, first)
        self.assertIs(first.v2_owner, app.hass)

    def test_port_rebinds_when_composed_v2_owner_changes(self):
        first_owner = _Owner()
        second_owner = _Owner()
        app = SimpleNamespace(hass=first_owner)
        first = get_or_create_execution_port(app)
        app.hass = second_owner
        second = get_or_create_execution_port(app)
        self.assertIsNot(first, second)
        self.assertIs(second.v2_owner, second_owner)
        self.assertIs(app.execution_port, second)

    def test_disable_prefers_canonical_output_state_code(self):
        owner = _Owner()
        # Compatibility switch intentionally remains stale ON; canonical V2
        # register proves OFF after the command.
        port = ExecutionPort(owner)
        result = asyncio.run(
            port.disable(
                _intent(),
                identity=SimpleNamespace(session_id="session", trace_id="trace"),
                reason="test_off",
            )
        )
        self.assertTrue(result.accepted)
        self.assertTrue(result.verified)
        self.assertEqual(owner.calls, [("turn_off",)])

    def test_unknown_canonical_output_code_uses_legacy_switch_fallback(self):
        owner = _Owner()

        async def turn_off_unknown():
            owner.calls.append(("turn_off",))
            owner.live["output_state_code_v2"] = "unknown"
            owner.live["switch"] = "off"
            return True

        owner.turn_off = turn_off_unknown
        result = asyncio.run(
            ExecutionPort(owner).disable(
                _intent(),
                identity=SimpleNamespace(session_id="session", trace_id="trace"),
                reason="test_unknown",
            )
        )
        # Unknown canonical V2 state uses the legacy switch compatibility path.
        self.assertTrue(result.verified)

    def test_migrated_runtime_helpers_have_no_direct_hass_writes(self):
        path = ROOT / "runtime" / "v2_runtime.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        migrated = {
            "_apply_phase_protection",
            "_apply_current_with_ocp",
            "_apply_current_with_startup_settle",
            "_apply_idle_protection",
            "_apply_controller_output_actions",
            "_hard_stop_charge",
            "_operator_pause_toggle",
            "power_toggle_handler",
        }
        forbidden = {
            "set_voltage",
            "set_current",
            "set_ovp",
            "set_ocp",
            "turn_on",
            "turn_off",
            "safe_enable_output",
        }
        violations = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name not in migrated:
                continue
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                    if child.func.attr in forbidden:
                        violations.append((node.name, child.func.attr))
        self.assertEqual([], violations)

    def test_start_modules_have_no_direct_hass_execution_writes(self):
        forbidden = (
            ".hass.safe_enable_output(",
            ".hass.turn_on(",
            ".hass.turn_off(",
            ".hass.set_voltage(",
            ".hass.set_current(",
            ".hass.set_ovp(",
            ".hass.set_ocp(",
        )
        for name in ("v2_startup.py", "v2_mix_mode.py"):
            source = (ROOT / name).read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, source, f"{name}: {token}")

    def test_start_modules_use_application_execution_port(self):
        for name in ("v2_startup.py", "v2_mix_mode.py"):
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("get_or_create_execution_port", source)
            self.assertIn(".enable(", source)
            self.assertIn(".disable(", source)

    def test_manual_uses_same_application_scoped_execution_port(self):
        source = inspect.getsource(__import__("manual_mode"))
        self.assertIn("get_or_create_execution_port(self.app)", source)
        self.assertNotIn(
            'ExecutionPort(getattr(self.app, "hass", None))',
            source,
        )

    def test_bootstrap_materializes_execution_port_before_manual_manager(self):
        source = (ROOT / "v2_bootstrap.py").read_text(encoding="utf-8")
        port_pos = source.index("get_or_create_execution_port(app)")
        manual_pos = source.index("ProductionManualSessionManager(app)")
        self.assertLess(port_pos, manual_pos)


if __name__ == "__main__":
    unittest.main()
