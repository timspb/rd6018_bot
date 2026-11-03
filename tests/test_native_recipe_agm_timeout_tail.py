"""Pinned AGM timeout tail current is consumed by the canonical MAIN decision."""
import tempfile
import unittest

from pb_domain import ChargeIntent
from production_controller import create_production_charge_host
from runtime.charge.decisions import AuthorityAction
from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from runtime.charge.programs.native_recipe_session import (
    native_target_parameters, select_native_recipe_version,
)
from runtime.charge.strategy.main_authority import decide_main_transition
from recovery_policy import RecoveryDecision


class _NoHardware:
    pass


class AGMTimeoutTailOverrideTests(unittest.TestCase):
    def test_effective_threshold_changes_only_pinned_agm_timeout(self):
        with tempfile.TemporaryDirectory() as root:
            library = NativeRecipeDraftLibrary(root)
            library.save("agm_copy", 1, {
                "schema": 1, "base_recipe_id": "native_agm_recovery",
                "execution_kind": "native_authority",
                "overrides": {"charge.main.agm_timeout_tail_current_a": 0.35},
            })
            host = create_production_charge_host(_NoHardware())
            host.start("AGM", 72)
            host._v2_intent = ChargeIntent.RECOVERY
            normal = native_target_parameters(host, "MAIN_POLICY")
            self.assertEqual(normal, {})
            host._native_recipe_session_selection = select_native_recipe_version(
                library, "agm_copy", 1, profile="AGM", intent="recovery"
            )
            params = native_target_parameters(host, "MAIN_POLICY")
            self.assertEqual(params["agm_timeout_tail_current_a"], 0.35)
            args = dict(
                profile="AGM", intent=ChargeIntent.RECOVERY,
                first_stage=None, policy_decision=RecoveryDecision.CONTINUE,
                seconds_since_current_min=None, required_tail_hold_s=7200.0,
                agm_stage_idx=0, agm_stage_count=4, desulf_attempts=0,
                max_desulf_attempts=4, main_elapsed_s=72 * 3600,
                main_limit_s=72 * 3600, current_a=0.30, is_cv=True,
            )
            default = decide_main_transition(**args)
            changed = decide_main_transition(
                **args, agm_timeout_tail_current_a=params["agm_timeout_tail_current_a"]
            )
            self.assertEqual(default.action, AuthorityAction.STOP_AND_DIAGNOSE)
            self.assertEqual(changed.action, AuthorityAction.ENTER_MIX)
            self.assertEqual(
                decide_main_transition(
                    **{**args, "is_cv": False},
                    agm_timeout_tail_current_a=params["agm_timeout_tail_current_a"]
                ).action,
                AuthorityAction.STOP_AND_DIAGNOSE
            )
            library.save("agm_copy", 2, {
                "schema": 1, "base_recipe_id": "native_agm_recovery",
                "execution_kind": "native_authority",
                "overrides": {"charge.main.agm_timeout_tail_current_a": 0.15},
            })
            self.assertEqual(
                native_target_parameters(host, "MAIN_POLICY")["agm_timeout_tail_current_a"],
                0.35,
            )

    def test_efb_cannot_save_agm_specific_threshold(self):
        with tempfile.TemporaryDirectory() as root:
            library = NativeRecipeDraftLibrary(root)
            with self.assertRaises(ValueError):
                library.save("efb_copy", 1, {
                    "schema": 1, "base_recipe_id": "native_efb_recovery",
                    "execution_kind": "native_authority",
                    "overrides": {"charge.main.agm_timeout_tail_current_a": 0.35},
                })
