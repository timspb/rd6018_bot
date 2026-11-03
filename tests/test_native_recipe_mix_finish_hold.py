"""Pinned MIX sticky finish hold reaches the original decision owner and UI timer."""
import tempfile
import types
import unittest
from unittest.mock import patch

from pb_domain import ChargeIntent
from production_controller import create_production_charge_host
from runtime.charge.decisions import AuthorityAction, AuthorityDecision
from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from runtime.charge.programs.native_recipe_session import select_native_recipe_version
from runtime.charge.runtime.mix_scaffold import apply_mix_authority_tick
from runtime.charge.runtime.support import stage_max_hours, target_finish_time
from runtime.charge.strategy.mix import decide_mix_transition
from recovery_policy import RecoveryDecision


class _NoHardware:
    pass


class MixFinishHoldOverridesTests(unittest.TestCase):
    def _host(self):
        host = create_production_charge_host(_NoHardware())
        host.start("EFB", 72)
        host._v2_intent = ChargeIntent.NORMAL
        host.current_stage = host.STAGE_MIX
        host.stage_start_time = 100.0
        host.finish_timer_start = 200.0
        return host

    def _runtime_value(self, host):
        record = types.SimpleNamespace(
            analysis=types.SimpleNamespace(metrics=types.SimpleNamespace(
                current_min_a=0.4, voltage_max_v=16.5,
            )),
            decision=types.SimpleNamespace(decision=RecoveryDecision.CONTINUE),
        )
        received = []
        def capture(**kw):
            received.append(kw)
            return AuthorityDecision(AuthorityAction.CONTINUE, "mix_hold_test")
        with patch("runtime.charge.strategy.mix.decide_mix_transition",
                   side_effect=capture):
            apply_mix_authority_tick(host, record=record, timestamp_s=1200.,
                                     voltage=16.2, current=0.6, temp=25.,
                                     ah=3., is_cv=True, is_cc=False, actions={})
        self.assertEqual(len(received), 1)
        return received[0]["finish_hold_s"]

    def test_existing_owner_uses_pinned_duration_and_existing_timer_matches(self):
        with tempfile.TemporaryDirectory() as root:
            lib = NativeRecipeDraftLibrary(root)
            lib.save("copy", 1, {
                "schema": 1, "base_recipe_id": "native_efb_normal",
                "execution_kind": "native_authority",
                "overrides": {"charge.mix.finish_hold_hours": 3.0},
            })
            host = self._host()
            self.assertEqual(self._runtime_value(host), 7200.0)
            self.assertEqual(stage_max_hours(host), 2.0)
            host._native_recipe_session_selection = select_native_recipe_version(
                lib, "copy", 1, profile="EFB", intent="normal",
            )
            self.assertEqual(self._runtime_value(host), 10800.0)
            self.assertEqual(stage_max_hours(host), 3.0)
            self.assertEqual(target_finish_time(host), 11000.0)
            lib.save("copy", 2, {
                "schema": 1, "base_recipe_id": "native_efb_normal",
                "execution_kind": "native_authority",
                "overrides": {"charge.mix.finish_hold_hours": 1.0},
            })
            self.assertEqual(self._runtime_value(host), 10800.0)
            self.assertEqual(
                decide_mix_transition(
                    profile="EFB", policy_decision=RecoveryDecision.CONTINUE,
                    active_elapsed_s=3000., finish_hold_started_at=200.,
                    now_s=11000., finish_hold_s=self._runtime_value(host),
                ).action,
                AuthorityAction.COMPLETE_TO_SAFE_WAIT,
            )

    def test_diagnostic_never_admits_mix_hold_override(self):
        with tempfile.TemporaryDirectory() as root:
            lib = NativeRecipeDraftLibrary(root)
            with self.assertRaises(ValueError):
                lib.save("diag", 1, {
                    "schema": 1, "base_recipe_id": "native_efb_diagnostic",
                    "execution_kind": "native_authority",
                    "overrides": {"charge.mix.finish_hold_hours": 1.0},
                })
