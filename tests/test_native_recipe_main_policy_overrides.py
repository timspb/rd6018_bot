"""Pinned MAIN policy is handed to the single canonical decision owner."""
import tempfile
import types
import unittest
from unittest.mock import patch

from pb_domain import ChargeIntent
from production_controller import create_production_charge_host
from runtime.charge.decisions import AuthorityAction, AuthorityDecision
from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from runtime.charge.programs.native_recipe_session import (
    native_target_parameters, select_native_recipe_version,
)
from runtime.charge.runtime.main_scaffold import apply_main_authority_tick


class _NoHardware:
    pass


def _record():
    return types.SimpleNamespace(
        decision=types.SimpleNamespace(decision=object()),
        analysis=types.SimpleNamespace(metrics=types.SimpleNamespace(
            seconds_since_current_min=600.0,
        )),
    )


class MainPolicyPinnedTests(unittest.TestCase):
    def _host(self, profile, intent):
        host = create_production_charge_host(_NoHardware())
        host.start(profile, 72)
        host._v2_intent = ChargeIntent(intent)
        host.antisulfate_count = 1
        host._agm_stage_idx = 0
        host.stage_start_time = 100.0
        return host

    def _decision_inputs(self, host):
        captured = []
        def decision(**kwargs):
            captured.append(kwargs)
            return AuthorityDecision(AuthorityAction.CONTINUE, "parity_probe")
        with patch("runtime.charge.strategy.main_authority.decide_main_transition",
                   side_effect=decision):
            result = apply_main_authority_tick(
                host, record=_record(), first_stage=None,
                timestamp_s=200.0, voltage=14.4, current=1.0,
                temp=25.0, ah=1.0, is_cv=True, actions={},
            )
        self.assertEqual(result.action, AuthorityAction.CONTINUE)
        self.assertEqual(len(captured), 1)
        return captured[0]

    def test_efb_pinned_timeout_tail_budget_and_new_version_isolation(self):
        with tempfile.TemporaryDirectory() as root:
            lib = NativeRecipeDraftLibrary(root)
            lib.save("copy", 1, {
                "schema": 1, "base_recipe_id": "native_efb_recovery",
                "execution_kind": "native_authority", "overrides": {
                    "charge.main.fallback_hours": 12.0,
                    "charge.main.standard_tail_hold_hours": 4.0,
                    "charge.main.standard_max_recovery_attempts": 1,
                },
            })
            host = self._host("EFB", "recovery")
            baseline = self._decision_inputs(host)
            host._native_recipe_session_selection = select_native_recipe_version(
                lib, "copy", 1, profile="EFB", intent="recovery")
            values = self._decision_inputs(host)
            self.assertEqual(values["main_limit_s"], 12 * 3600)
            self.assertEqual(values["required_tail_hold_s"], 4 * 3600)
            self.assertEqual(values["max_desulf_attempts"], 1)
            self.assertEqual(baseline["main_limit_s"], 72 * 3600)
            self.assertEqual(baseline["required_tail_hold_s"], 3 * 3600)
            self.assertEqual(baseline["max_desulf_attempts"], 3)
            lib.save("copy", 2, {
                "schema": 1, "base_recipe_id": "native_efb_recovery",
                "execution_kind": "native_authority",
                "overrides": {"charge.main.fallback_hours": 24.0},
            })
            self.assertEqual({k:v for k,v in self._decision_inputs(host).items() if k != "policy_decision"},
                             {k:v for k,v in values.items() if k != "policy_decision"})

    def test_agm_specific_keys_and_cross_profile_rejection(self):
        with tempfile.TemporaryDirectory() as root:
            lib = NativeRecipeDraftLibrary(root)
            lib.save("agm", 1, {
                "schema": 1, "base_recipe_id": "native_agm_recovery",
                "execution_kind": "native_authority", "overrides": {
                    "charge.main.agm_tail_hold_hours": 3.0,
                    "charge.main.agm_max_recovery_attempts": 2,
                },
            })
            host = self._host("AGM", "recovery")
            selected = select_native_recipe_version(
                lib, "agm", 1, profile="AGM", intent="recovery")
            host._native_recipe_session_selection = selected
            args = self._decision_inputs(host)
            self.assertEqual(args["required_tail_hold_s"], 3 * 3600)
            self.assertEqual(args["max_desulf_attempts"], 2)
            efb = self._host("EFB", "recovery")
            efb._native_recipe_session_selection = selected
            with self.assertRaises(ValueError):
                self._decision_inputs(efb)

    def test_unwired_mix_parameter_still_rejected_at_selection(self):
        with tempfile.TemporaryDirectory() as root:
            lib = NativeRecipeDraftLibrary(root)
            lib.save("unwired", 1, {
                "schema": 1, "base_recipe_id": "native_efb_normal",
                "execution_kind": "native_authority",
                "overrides": {"charge.mix.finish_hold_hours": 4.0},
            })
            with self.assertRaises(ValueError):
                select_native_recipe_version(
                    lib, "unwired", 1, profile="EFB", intent="normal",
                )
