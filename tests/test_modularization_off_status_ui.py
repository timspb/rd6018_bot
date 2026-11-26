import ast
from dataclasses import dataclass
from pathlib import Path
import unittest

from runtime.ui.components.hmi_values import format_operator_off_conditions


@dataclass
class FakeOperatorOffConditions:
    voltage_ge: float = None
    voltage_le: float = None
    current_le: float = None
    current_ge: float = None
    time_sec: float = None
    start_time: float = 0.0

    def has_condition(self):
        return any(value is not None for value in (
            self.voltage_ge, self.voltage_le, self.current_le,
            self.current_ge, self.time_sec,
        ))


class OperatorOffStatusProjectionTests(unittest.TestCase):
    def test_inactive_projection_is_empty(self):
        state = FakeOperatorOffConditions()
        self.assertFalse(state.has_condition())
        self.assertEqual("", format_operator_off_conditions(state, now_s=100.0))

    def test_equal_voltage_and_current_thresholds_use_reached_format(self):
        state = FakeOperatorOffConditions(
            voltage_ge=14.2, voltage_le=14.204,
            current_le=1.25, current_ge=1.256,
        )
        self.assertEqual(
            "⏹ ВЫКЛ ПО УСЛОВИЮ: при достижении V 14.20 В, при достижении I 1.25 А",
            format_operator_off_conditions(state, now_s=100.0),
        )

    def test_distinct_thresholds_keep_voltage_then_current_order(self):
        state = FakeOperatorOffConditions(
            voltage_ge=15.25, voltage_le=12.345,
            current_le=0.3, current_ge=2.0,
        )
        self.assertEqual(
            "⏹ ВЫКЛ ПО УСЛОВИЮ: при V≥15.2 В, при V≤12.3 В, "
            "при I≤0.30 А, при I≥2.00 А",
            format_operator_off_conditions(state, now_s=100.0),
        )

    def test_timer_expired_and_future(self):
        expired = FakeOperatorOffConditions(time_sec=3600, start_time=100)
        future = FakeOperatorOffConditions(time_sec=3600, start_time=100)
        self.assertEqual(
            "⏹ ВЫКЛ ПО УСЛОВИЮ: таймер истёк",
            format_operator_off_conditions(expired, now_s=3700),
        )
        self.assertEqual(
            "⏹ ВЫКЛ ПО УСЛОВИЮ: таймер 1:00 | осталось до выкл: 0:30",
            format_operator_off_conditions(future, now_s=3700 - 1800),
        )

    def test_timer_remaining_uses_hh_mm_flooring(self):
        state = FakeOperatorOffConditions(time_sec=5 * 3600 + 17 * 60, start_time=100)
        self.assertEqual(
            "⏹ ВЫКЛ ПО УСЛОВИЮ: таймер 5:17 | осталось до выкл: 2:02",
            format_operator_off_conditions(state, now_s=100 + 3 * 3600 + 14 * 60 + 59),
        )

    def test_no_timer_does_not_add_timer_text(self):
        state = FakeOperatorOffConditions(voltage_ge=16.2)
        self.assertEqual(
            "⏹ ВЫКЛ ПО УСЛОВИЮ: при V≥16.2 В",
            format_operator_off_conditions(state, now_s=100.0),
        )

    def test_multicondition_order_and_legacy_formula_parity(self):
        state = FakeOperatorOffConditions(
            voltage_ge=14.4, voltage_le=13.1,
            current_le=0.5, current_ge=1.5,
            time_sec=2 * 3600 + 30 * 60, start_time=100,
        )
        # Golden output from the pre-extraction formatter at this fixed time.
        self.assertEqual(
            "⏹ ВЫКЛ ПО УСЛОВИЮ: при V≥14.4 В, при V≤13.1 В, "
            "при I≤0.50 А, при I≥1.50 А, таймер 2:30 | осталось до выкл: 1:30",
            format_operator_off_conditions(state, now_s=3700),
        )


class OperatorOffStatusBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime_source = Path("runtime/production_runtime.py").read_text(encoding="utf-8")
        cls.ui_source = Path("runtime/ui/components/hmi_values.py").read_text(encoding="utf-8")
        cls.runtime_tree = ast.parse(cls.runtime_source)
        cls.ui_tree = ast.parse(cls.ui_source)

    def test_compatibility_wrapper_is_thin_and_preserves_signature(self):
        wrapper = next(node for node in self.runtime_tree.body
                       if isinstance(node, ast.FunctionDef)
                       and node.name == "_format_manual_off_for_dashboard")
        self.assertEqual([], wrapper.args.args)
        self.assertFalse(wrapper.args.kwonlyargs)
        source = ast.get_source_segment(self.runtime_source, wrapper)
        self.assertIn("_has_manual_off_condition()", source)
        self.assertIn("format_operator_off_conditions", source)
        self.assertIn("time.time()", source)
        self.assertEqual(1, source.count("format_operator_off_conditions("))
        self.assertNotIn("voltage_ge", source)
        self.assertNotIn("current_le", source)
        self.assertNotIn("remaining_sec", source)

    def test_ui_projection_has_no_production_or_physical_or_filesystem_imports(self):
        projection = next(node for node in self.ui_tree.body
                          if isinstance(node, ast.FunctionDef)
                          and node.name == "format_operator_off_conditions")
        forbidden = {"production_runtime", "hass_api", "runtime.physical", "os",
                     "pathlib", "subprocess"}
        imported = set()
        for node in ast.walk(projection):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        self.assertFalse(forbidden & imported, forbidden & imported)
        self.assertNotIn("open", {node.id for node in ast.walk(projection)
                                   if isinstance(node, ast.Name)})
        self.assertEqual("state", projection.args.args[0].arg)
        self.assertEqual(["now_s"], [arg.arg for arg in projection.args.kwonlyargs])


if __name__ == "__main__":
    unittest.main()
