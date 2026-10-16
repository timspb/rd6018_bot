import ast
import unittest
from pathlib import Path

from runtime.charge.link_session_recovery import (
    RecoveryAction,
    RecoveryAuthorizationInput,
    RecoveryRoute,
    RecoveryRouteInput,
    authorize_recovery_action,
    choose_recovery_route,
)


def route_input(**overrides):
    values = dict(
        was_unavailable=True,
        stage="MAIN",
        idle_stage="IDLE",
        done_stage="DONE",
        cooling_stage="COOLING",
        output_on=False,
        current_a=0.0,
        temperature_available=True,
    )
    values.update(overrides)
    return RecoveryRouteInput(**values)


def auth_input(route, **overrides):
    values = dict(
        route=route,
        restored=True,
        auto_enable_authorized=True,
        safe_wait=False,
        ovp_triggered=False,
        ocp_triggered=False,
        input_voltage_ok=True,
    )
    values.update(overrides)
    return RecoveryAuthorizationInput(**values)


class LinkSessionRecoveryPolicyTests(unittest.TestCase):
    def test_three_routes_and_route_declines(self):
        self.assertEqual(choose_recovery_route(route_input()), RecoveryRoute.ACTIVE_LINK)
        self.assertEqual(
            choose_recovery_route(route_input(stage="IDLE")), RecoveryRoute.IDLE_LINK
        )
        self.assertEqual(
            choose_recovery_route(route_input(
                was_unavailable=False, stage="IDLE", output_on=True, current_a=0.06
            )),
            RecoveryRoute.IDLE_OUTPUT_ON,
        )
        self.assertEqual(choose_recovery_route(route_input(temperature_available=False)), RecoveryRoute.NONE)
        self.assertEqual(choose_recovery_route(route_input(stage="DONE")), RecoveryRoute.NONE)
        self.assertEqual(choose_recovery_route(route_input(stage="COOLING")), RecoveryRoute.NONE)
        self.assertEqual(choose_recovery_route(route_input(output_on=True)), RecoveryRoute.NONE)
        self.assertEqual(choose_recovery_route(route_input(stage="IDLE", was_unavailable=False)), RecoveryRoute.NONE)
        self.assertEqual(
            choose_recovery_route(route_input(
                was_unavailable=False, stage="IDLE", output_on=True, current_a=0.05
            )),
            RecoveryRoute.NONE,
        )

    def test_post_restore_authority_protection_and_action_matrix(self):
        self.assertEqual(
            authorize_recovery_action(auth_input(RecoveryRoute.ACTIVE_LINK)),
            RecoveryAction.REENABLE_ACTIVE,
        )
        self.assertEqual(
            authorize_recovery_action(auth_input(RecoveryRoute.IDLE_LINK)),
            RecoveryAction.ENABLE_RESTORED,
        )
        self.assertEqual(
            authorize_recovery_action(auth_input(RecoveryRoute.IDLE_OUTPUT_ON)),
            RecoveryAction.PROGRAM_RETAINED_OUTPUT,
        )
        for changes in (
            {"restored": False},
            {"auto_enable_authorized": False},
            {"ovp_triggered": True},
            {"ocp_triggered": True},
            {"input_voltage_ok": False},
        ):
            self.assertEqual(
                authorize_recovery_action(auth_input(RecoveryRoute.IDLE_LINK, **changes)),
                RecoveryAction.SKIP,
            )
        self.assertEqual(
            authorize_recovery_action(auth_input(RecoveryRoute.IDLE_LINK, safe_wait=True)),
            RecoveryAction.SAFE_WAIT_OFF,
        )
        self.assertEqual(
            authorize_recovery_action(auth_input(RecoveryRoute.IDLE_OUTPUT_ON, safe_wait=True)),
            RecoveryAction.SAFE_WAIT_OFF,
        )
        self.assertEqual(
            authorize_recovery_action(auth_input(RecoveryRoute.ACTIVE_LINK, ovp_triggered=True)),
            RecoveryAction.SKIP,
        )
        self.assertEqual(
            authorize_recovery_action(auth_input(RecoveryRoute.ACTIVE_LINK, ocp_triggered=True)),
            RecoveryAction.SKIP,
        )
        self.assertEqual(
            authorize_recovery_action(auth_input(RecoveryRoute.ACTIVE_LINK, input_voltage_ok=False)),
            RecoveryAction.SKIP,
        )


    def test_combinatorial_parity_with_preexisting_restoration_branches(self):
        """Old inline conditions are the oracle; no new route or Output ON."""
        from itertools import product

        stages = ("IDLE", "DONE", "COOLING", "MAIN", "SAFE_WAIT")
        for lost, stage, output, current, temp_ok, ovp, ocp, power_ok, restored, allowed in product(
            (False, True), stages, (False, True), (0.0, 0.05, 0.051),
            (False, True), (False, True), (False, True),
            (False, True), (False, True), (False, True),
        ):
            # Mirror the three prior production-runtime branches in priority order.
            expected = RecoveryAction.SKIP
            if temp_ok and lost and stage not in ("IDLE", "DONE", "COOLING") and not output:
                if not ovp and not ocp and power_ok:
                    expected = RecoveryAction.REENABLE_ACTIVE
            elif temp_ok and lost and stage == "IDLE":
                if restored and allowed and not ovp and not ocp and power_ok:
                    expected = RecoveryAction.SAFE_WAIT_OFF if stage == "SAFE_WAIT" else RecoveryAction.ENABLE_RESTORED
            elif temp_ok and not lost and stage == "IDLE" and output and current > 0.05:
                if restored and allowed and not ovp and not ocp and power_ok:
                    expected = RecoveryAction.PROGRAM_RETAINED_OUTPUT
            route = choose_recovery_route(route_input(
                was_unavailable=lost, stage=stage, output_on=output,
                current_a=current, temperature_available=temp_ok,
            ))
            actual = authorize_recovery_action(auth_input(
                route, restored=restored, auto_enable_authorized=allowed,
                safe_wait=(stage == "SAFE_WAIT"), ovp_triggered=ovp,
                ocp_triggered=ocp, input_voltage_ok=power_ok,
            ))
            self.assertEqual(actual, expected, (
                lost, stage, output, current, temp_ok, ovp, ocp,
                power_ok, restored, allowed,
            ))

    def test_policy_is_pure_and_production_wires_all_routes(self):
        policy_path = Path("runtime/charge/link_session_recovery.py")
        tree = ast.parse(policy_path.read_text(encoding="utf-8"))
        imports = [
            node.module for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module not in {"__future__", "dataclasses", "enum"}
        ]
        imports += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
        self.assertFalse(imports, "policy must not import clients, logger, or production code")
        source = Path("runtime/production_runtime.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("choose_recovery_route(RecoveryRouteInput("), 1)
        self.assertIn("recovery_route is RecoveryRoute.ACTIVE_LINK", source)
        self.assertIn("recovery_route is RecoveryRoute.IDLE_LINK", source)
        self.assertIn("recovery_route is RecoveryRoute.IDLE_OUTPUT_ON", source)
        self.assertIn("try_restore_session(", source)
        self.assertIn("restore_allows_auto_enable", source)
        self.assertLess(source.index("if _operator_pause_active():", source.index("# Explicit operator pause")),
                        source.index("recovery_route = choose_recovery_route"))
        self.assertIn('output_on = str(output_switch or "").lower() == "on"', source)
        self.assertNotIn("request_verified_on", policy_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
