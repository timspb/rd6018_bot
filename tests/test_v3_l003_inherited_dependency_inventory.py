from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
V2_PATH = ROOT / "charge_controller.py"
LEGACY_PATH = ROOT / "charge_logic.py"

EXPECTED_HISTORICAL_SUPPORT_CLOSURE = set()

EXPECTED_EXTERNAL_INHERITED_SURFACE = set()

EXPECTED_CANONICAL_CLASS_CONSTANTS = {
    "PROFILE_AGM",
    "PROFILE_CA",
    "PROFILE_CUSTOM",
    "PROFILE_EFB",
    "STAGE_COOLING",
    "STAGE_DESULFATION",
    "STAGE_DONE",
    "STAGE_IDLE",
    "STAGE_MAIN",
    "STAGE_MIX",
    "STAGE_PREP",
    "STAGE_SAFE_WAIT",
}


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
    return next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == name
    )


def _methods(node: ast.ClassDef) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        item.name: item
        for item in node.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _self_calls(node: ast.AST) -> set[str]:
    result: set[str] = set()
    for item in ast.walk(node):
        if not isinstance(item, ast.Call):
            continue
        func = item.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "self"
        ):
            result.add(func.attr)
    return result


def _super_calls(node: ast.AST) -> set[str]:
    result: set[str] = set()
    for item in ast.walk(node):
        if not isinstance(item, ast.Call):
            continue
        func = item.func
        if not isinstance(func, ast.Attribute):
            continue
        owner = func.value
        if (
            isinstance(owner, ast.Call)
            and isinstance(owner.func, ast.Name)
            and owner.func.id == "super"
        ):
            result.add(func.attr)
    return result


def _production_python_paths() -> list[Path]:
    return [
        path
        for path in ROOT.rglob("*.py")
        if "tests" not in path.parts
        and path not in {LEGACY_PATH, V2_PATH}
    ]


class L003InheritedDependencyInventoryTests(unittest.TestCase):
    def test_exact_historical_support_closure_is_bounded_and_tick_free(self) -> None:
        v2_tree = ast.parse(V2_PATH.read_text(encoding="utf-8"))
        legacy_tree = ast.parse(LEGACY_PATH.read_text(encoding="utf-8"))
        v2 = _class(v2_tree, "ChargeControllerV2")
        legacy = _class(legacy_tree, "ChargeController")

        self.assertEqual(
            [base.id for base in v2.bases if isinstance(base, ast.Name)],
            [],
        )

        v2_methods = _methods(v2)
        legacy_methods = _methods(legacy)

        roots = _super_calls(v2)
        for method in v2_methods.values():
            roots.update(
                name
                for name in _self_calls(method)
                if name in legacy_methods and name not in v2_methods
            )

        closure: set[str] = set()
        pending = list(roots)
        while pending:
            name = pending.pop()
            if name in closure or name not in legacy_methods:
                continue
            closure.add(name)
            for dependency in _self_calls(legacy_methods[name]):
                if dependency in v2_methods:
                    continue
                if dependency in legacy_methods and dependency not in closure:
                    pending.append(dependency)

        self.assertNotIn("tick", closure)
        self.assertEqual(closure, EXPECTED_HISTORICAL_SUPPORT_CLOSURE)

    def test_external_production_references_to_inherited_surface_are_bounded(self) -> None:
        v2_tree = ast.parse(V2_PATH.read_text(encoding="utf-8"))
        legacy_tree = ast.parse(LEGACY_PATH.read_text(encoding="utf-8"))
        v2_methods = _methods(_class(v2_tree, "ChargeControllerV2"))
        legacy_methods = _methods(_class(legacy_tree, "ChargeController"))
        historical_only = set(legacy_methods) - set(v2_methods)

        attributes: set[str] = set()
        for path in _production_python_paths():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            attributes.update(
                node.attr
                for node in ast.walk(tree)
                if isinstance(node, ast.Attribute)
            )

        inherited_external = historical_only & attributes
        self.assertNotIn("tick", inherited_external)
        self.assertEqual(
            inherited_external,
            EXPECTED_EXTERNAL_INHERITED_SURFACE,
        )

    def test_stage_and_profile_constants_are_owned_by_v2_state_module(self) -> None:
        v2_tree = ast.parse(V2_PATH.read_text(encoding="utf-8"))
        legacy_tree = ast.parse(LEGACY_PATH.read_text(encoding="utf-8"))
        v2 = _class(v2_tree, "ChargeControllerV2")
        legacy = _class(legacy_tree, "ChargeController")

        legacy_constants = {
            node.targets[0].id
            for node in legacy.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and (
                node.targets[0].id.startswith("STAGE_")
                or node.targets[0].id.startswith("PROFILE_")
            )
        }
        v2_constants = {
            node.targets[0].id
            for node in v2.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        }

        self.assertEqual(
            legacy_constants & v2_constants,
            EXPECTED_CANONICAL_CLASS_CONSTANTS,
        )

        referenced: set[str] = set()
        for path in [V2_PATH, *_production_python_paths()]:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            referenced.update(
                node.attr
                for node in ast.walk(tree)
                if isinstance(node, ast.Attribute)
            )
        self.assertEqual((legacy_constants - v2_constants) & referenced, set())

    def test_controller_state_bootstrap_matches_historical_shape(self) -> None:
        from charge_controller import ChargeControllerV2
        from charge_logic import ChargeController

        hass = object()

        def notify(_: str) -> None:
            return None

        historical = ChargeController(hass, notify_cb=notify)
        current = ChargeControllerV2(hass, notify_cb=notify)

        for name, expected in historical.__dict__.items():
            with self.subTest(name=name):
                self.assertIn(name, current.__dict__)
                actual = current.__dict__[name]
                if hasattr(expected, "maxlen"):
                    self.assertEqual(getattr(actual, "maxlen", None), expected.maxlen)
                    self.assertEqual(list(actual), list(expected))
                else:
                    self.assertEqual(actual, expected)

    def test_target_temperature_and_protection_parity(self) -> None:
        from charge_controller import ChargeControllerV2
        from charge_logic import ChargeController

        for profile in ("Ca/Ca", "EFB", "AGM", "Custom"):
            for capacity in (60, 90):
                for temp in (5.0, 25.0, 40.0):
                    historical = ChargeController(object())
                    current = ChargeControllerV2(object())
                    for controller in (historical, current):
                        controller.battery_type = profile
                        controller.ah_capacity = capacity
                        controller._agm_stage_idx = 2
                        controller._custom_main_voltage = 14.9
                        controller._custom_main_current = 4.5

                    for stage in (
                        historical.STAGE_PREP,
                        historical.STAGE_MAIN,
                        historical.STAGE_DESULFATION,
                        historical.STAGE_MIX,
                    ):
                        historical.current_stage = stage
                        current.current_stage = stage
                        with self.subTest(profile=profile, capacity=capacity, temp=temp, stage=stage):
                            self.assertEqual(
                                current._get_target_v_i(temp),
                                historical._get_target_v_i(temp),
                            )

                    historical_actions: dict[str, float] = {}
                    current_actions: dict[str, float] = {}
                    historical._add_phase_limits(historical_actions, 14.8, 6.0)
                    current._add_phase_limits(current_actions, 14.8, 6.0)
                    self.assertEqual(current_actions, historical_actions)
                    self.assertEqual(
                        current._phase_current_limit,
                        historical._phase_current_limit,
                    )

                    historical_actions = {}
                    current_actions = {}
                    historical._add_desulf_limits(historical_actions, 16.3, 1.2)
                    current._add_desulf_limits(current_actions, 16.3, 1.2)
                    self.assertEqual(current_actions, historical_actions)
                    self.assertEqual(
                        current._phase_current_limit,
                        historical._phase_current_limit,
                    )

    def test_post_charge_and_log_helpers_match_historical_behavior(self) -> None:
        from charge_controller import ChargeControllerV2
        from charge_logic import ChargeController

        for profile in ("Ca/Ca", "EFB", "AGM", "Custom"):
            historical = ChargeController(object())
            current = ChargeControllerV2(object())
            historical.battery_type = profile
            current.battery_type = profile
            with self.subTest(profile=profile):
                self.assertEqual(
                    current._post_charge_profile_params(),
                    historical._post_charge_profile_params(),
                )

        historical = ChargeController(object())
        current = ChargeControllerV2(object())
        for controller in (historical, current):
            controller.current_stage = controller.STAGE_SAFE_WAIT
            controller.stage_start_time = 100.0
            controller._stage_start_ah = 3.5

        current._record_safe_wait_sample(300.0, 13.2, 0.01, 24.0)
        historical._record_safe_wait_sample(300.0, 13.2, 0.01, 24.0)
        self.assertEqual(
            list(current._safe_wait_v_samples),
            list(historical._safe_wait_v_samples),
        )
        self.assertEqual(
            current._last_safe_wait_sample,
            historical._last_safe_wait_sample,
        )
        self.assertEqual(
            current._make_log_event_end(460.0, 5.0, 14.2, 1.2, 25.0, "test"),
            historical._make_log_event_end(460.0, 5.0, 14.2, 1.2, 25.0, "test"),
        )

    def test_runtime_support_helpers_use_canonical_limits(self) -> None:
        from charge_controller import ChargeControllerV2

        controller = ChargeControllerV2(object())
        controller.battery_type = controller.PROFILE_EFB
        controller.current_stage = controller.STAGE_MIX
        controller.stage_start_time = 100.0

        self.assertEqual(controller._get_stage_max_hours(), 24.0)
        self.assertEqual(
            controller._get_target_finish_time(),
            100.0 + 24.0 * 3600.0,
        )
        self.assertIn("Mix 24h", controller._session_rules_summary())

        controller.i_min_recorded = 1.0
        self.assertAlmostEqual(controller._mix_current_delta_threshold(), 0.30)
        self.assertFalse(controller._exit_cv_condition(1.29))
        self.assertTrue(controller._exit_cv_condition(1.30))

        controller.v_max_recorded = 16.5
        self.assertFalse(controller._exit_cc_condition(16.48))
        self.assertTrue(controller._exit_cc_condition(16.47))

    def test_v2_diagnostics_use_canonical_policy_and_preserve_risk_heuristic(self) -> None:
        from charge_controller import ChargeControllerV2

        controller = ChargeControllerV2(object())
        controller.battery_type = controller.PROFILE_EFB
        controller.current_stage = controller.STAGE_MIX
        controller.stage_start_time = 1_000.0
        controller.total_start_time = 1_000.0

        snapshot = controller.get_ai_stage_snapshot(25.0)
        self.assertEqual(
            snapshot["mix_exit_policy"]["fallback_limit_hours"],
            24.0,
        )
        self.assertIn("24", snapshot["summary"])

        controller.current_stage = controller.STAGE_PREP
        now = 1_000_000.0
        controller.stage_start_time = now - 2 * 3600.0
        controller._stage_start_voltage = 10.7
        controller._stage_start_current = 0.45
        controller._stage_start_temp = 24.0
        controller._stage_start_ah = 0.0
        controller._analytics_history.clear()
        risk = controller._bank_fault_risk_snapshot(
            now,
            11.15,
            0.32,
            25.1,
            1.4,
        )
        self.assertIsNotNone(risk)
        self.assertEqual(risk["status"], "high")
        self.assertGreaterEqual(risk["score"], 70)
        self.assertIn("prep_start_low=10.70V", risk["reasons"])

    def test_charge_controller_has_no_historical_import_edge(self) -> None:
        tree = ast.parse(V2_PATH.read_text(encoding="utf-8"))
        imports: list[tuple[str, tuple[str, ...]]] = []
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module == "charge_logic":
                imports.append((node.module, tuple(alias.name for alias in node.names)))
        self.assertEqual(imports, [])


if __name__ == "__main__":
    unittest.main()
