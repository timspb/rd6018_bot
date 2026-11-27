"""Fake-only parity through the existing production charge-stage dispatch."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from application.charge_session_tick import run_charge_session_tick
from charge_controller import ManagedChargeController
from runtime.charge.decisions import AuthorityAction, AuthorityDecision
from runtime.charge.strategy.main_variables import (
    AGM_STAGE_VOLTAGES_V,
    agm_tail_hold_seconds,
    main_fallback_seconds,
    standard_tail_hold_seconds,
)
from runtime.charge.strategy.mix_variables import mix_max_active_seconds
from runtime.charge.strategy.prep import select_prep_target
from runtime.charge.strategy.prep_variables import PREP_VOLTAGE_V
from recovery_policy import RecoveryDecision
from signal_analyzer import SignalAnalysis, SignalMetrics, SignalSample
from runtime.charge.evidence.first_stage import tail_current_threshold_a


class _NoPhysicalAdapter:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def unexpected(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            raise AssertionError(f"physical adapter call: {name}")
        return unexpected


def _analysis(now, *, current=0.4, current_min=0.4, seconds_since_min=0.0,
              voltage_max=14.8, delta_voltage=0.0):
    metrics = SignalMetrics(
        d_voltage_v_per_min=0.0, d_current_a_per_min=0.0, d_temp_c_per_min=0.0,
        current_min_a=current_min, seconds_since_current_min=seconds_since_min,
        delta_current_from_min_a=current-current_min,
        reversal_threshold_a=max(0.03, current_min * 0.30),
        voltage_max_v=voltage_max,
        delta_voltage_from_max_v=delta_voltage,
        current_plateau_span_a=0.0, current_plateau_center_a=current,
        reversal_confirmations=0, main_stable_hold_s=seconds_since_min,
    )
    return SignalAnalysis(
        sample=SignalSample(now, 14.8, current, 25.0, is_cv=True, is_cc=False),
        metrics=metrics, events=frozenset(),
    )


class _FixedRuntime:
    def __init__(self, analysis, decision=RecoveryDecision.CONTINUE):
        self.analysis = analysis
        self.decision = decision

    def observe(self, point, *, legacy_actions=None, output_is_on=True):
        return SimpleNamespace(
            point=point, analysis=self.analysis,
            decision=SimpleNamespace(decision=self.decision, reason="fixture"),
            legacy_effect="continue", disagreement=None,
        )

    def summary(self):
        return {"samples": 1, "decision_counts": {}, "disagreement_counts": {}}


class RD6018P5StagePathParityTests(unittest.IsolatedAsyncioTestCase):
    def _host(self, profile, stage=None):
        hass = _NoPhysicalAdapter()
        host = ManagedChargeController(hass)
        host.battery_type = profile
        host.ah_capacity = 70
        host.current_stage = stage or host.STAGE_MAIN
        host.stage_start_time = 900.0
        host.total_start_time = 900.0
        host._stage_start_ah = 1.0
        host._v2_target_voltage_v = 14.8
        host._v2_trace_session_id = "p5-parity"
        host._v2_trace_started_at = 900.0
        host._last_known_output_on = True
        host._save_session = lambda *args, **kwargs: None
        return host, hass

    async def _tick(self, host, *, now, voltage=14.8, current=0.4, is_cv=True):
        with patch("time.time", return_value=now):
            return await run_charge_session_tick(
                host, voltage, current, 25.0, is_cv, 2.0, True,
                is_cc=not is_cv,
            )

    async def test_main_profile_routing_and_agm_step_effect(self):
        for profile in ("Ca/Ca", "EFB", "AGM"):
            with self.subTest(profile=profile):
                host, hass = self._host(profile)
                host._v2_runtime = _FixedRuntime(_analysis(1000.0))
                action = (AuthorityAction.ADVANCE_AGM_STEP if profile == "AGM"
                          else AuthorityAction.CONTINUE)
                decision = AuthorityDecision(action, "p5-fixture")
                with patch(
                    "runtime.charge.strategy.main_authority.decide_main_transition",
                    return_value=decision,
                ) as decide:
                    actions = await self._tick(host, now=1000.0)

                self.assertEqual(decide.call_args.kwargs["profile"], profile)
                self.assertEqual(
                    actions["recovery_shadow"]["authority_decision"],
                    {"action": action.value, "reason": "p5-fixture"},
                )
                self.assertEqual(host.current_stage, host.STAGE_MAIN)
                if profile == "AGM":
                    self.assertEqual(host._agm_stage_idx, 1)
                    self.assertEqual(actions["log_event"], "V2_AGM_STEP_2")
                    self.assertIn("set_voltage", actions)
                    self.assertIn("set_current", actions)
                else:
                    self.assertEqual(host._agm_stage_idx, 0)
                self.assertEqual(hass.calls, [])

    async def test_real_main_strategy_advances_agm_step_from_tail_evidence(self):
        from runtime.charge.strategy.main_authority import decide_main_transition

        now = 1000.0
        host, hass = self._host("AGM")
        required_hold = agm_tail_hold_seconds()
        tail_current = tail_current_threshold_a("AGM", host.ah_capacity)
        host._v2_runtime = _FixedRuntime(_analysis(
            now, current=tail_current, current_min=tail_current,
            seconds_since_min=required_hold,
        ))

        with patch(
            "runtime.charge.strategy.main_authority.decide_main_transition",
            wraps=decide_main_transition,
        ) as decide:
            actions = await self._tick(host, now=now, current=tail_current)

        self.assertEqual(decide.call_count, 1)
        self.assertEqual(decide.call_args.kwargs["profile"], "AGM")
        self.assertAlmostEqual(
            decide.call_args.kwargs["required_tail_hold_s"], required_hold
        )
        self.assertAlmostEqual(
            decide.call_args.kwargs["seconds_since_current_min"], required_hold
        )
        self.assertEqual(
            actions["recovery_shadow"]["authority_decision"],
            {
                "action": AuthorityAction.ADVANCE_AGM_STEP.value,
                "reason": "agm_tail_hold_complete_advance_voltage_step",
            },
        )
        self.assertEqual(host.current_stage, host.STAGE_MAIN)
        self.assertEqual(host._agm_stage_idx, 1)
        self.assertEqual(actions["log_event"], "V2_AGM_STEP_2")
        self.assertEqual(
            actions["set_voltage"], float(AGM_STAGE_VOLTAGES_V.default[1])
        )
        self.assertIn("set_current", actions)
        self.assertEqual(hass.calls, [])

    async def test_real_main_strategy_dispatches_efb_mix_after_configured_imin_hold(self):
        from runtime.charge.strategy.main_authority import decide_main_transition

        required_hold = standard_tail_hold_seconds()
        host, hass = self._host("EFB")
        accepted_minimum = tail_current_threshold_a("EFB", host.ah_capacity)
        observed_ages = (required_hold - 1.0, 0.0, required_hold)
        observed_decisions = []

        with patch(
            "runtime.charge.strategy.main_authority.decide_main_transition",
            wraps=decide_main_transition,
        ) as decide:
            for index, age in enumerate(observed_ages):
                host._v2_runtime = _FixedRuntime(_analysis(
                    1000.0 + index * 60.0,
                    current=accepted_minimum,
                    current_min=accepted_minimum,
                    seconds_since_min=age,
                ))
                actions = await self._tick(
                    host, now=1000.0 + index * 60.0, current=accepted_minimum
                )
                observed_decisions.append(
                    actions["recovery_shadow"]["authority_decision"]["action"]
                )
                if index < len(observed_ages) - 1:
                    self.assertEqual(host.current_stage, host.STAGE_MAIN)

        self.assertEqual(decide.call_count, len(observed_ages))
        self.assertEqual(
            [call.kwargs["seconds_since_current_min"] for call in decide.call_args_list],
            list(observed_ages),
        )
        self.assertTrue(all(
            call.kwargs["required_tail_hold_s"] == required_hold
            for call in decide.call_args_list
        ))
        self.assertEqual(observed_decisions, [
            AuthorityAction.CONTINUE.value,
            AuthorityAction.CONTINUE.value,
            AuthorityAction.ENTER_MIX.value,
        ])
        self.assertEqual(
            actions["recovery_shadow"]["authority_decision"],
            {
                "action": AuthorityAction.ENTER_MIX.value,
                "reason": "main_tail_hold_complete_recovery_mix",
            },
        )
        self.assertEqual(host.current_stage, host.STAGE_MIX)
        self.assertTrue(actions["log_event"].startswith("MIX_STARTED | reason="))
        self.assertIn("set_voltage", actions)
        self.assertIn("set_current", actions)
        self.assertNotIn("turn_on", actions)
        self.assertEqual(hass.calls, [])

    async def test_real_analyzer_imin_age_reaches_main_strategy(self):
        host, hass = self._host("EFB")
        observed = []
        decision = AuthorityDecision(AuthorityAction.CONTINUE, "p5-imin")
        with patch(
            "runtime.charge.strategy.main_authority.decide_main_transition",
            side_effect=lambda **kwargs: (observed.append(kwargs) or decision),
        ):
            for now, current in ((1000.0, 0.40), (1060.0, 0.35), (1180.0, 0.35)):
                await self._tick(host, now=now, current=current)

        self.assertEqual(len(observed), 3)
        self.assertAlmostEqual(observed[-1]["seconds_since_current_min"], 120.0)
        self.assertEqual(host._v2_runtime.tracker._analyzer._current_min_a, 0.35)
        self.assertEqual(host.current_stage, host.STAGE_MAIN)
        self.assertEqual(hass.calls, [])

    async def test_main_fallback_boundary_dispatches_existing_mix_effect(self):
        from runtime.charge.strategy.main_authority import decide_main_transition

        now = 900.0 + main_fallback_seconds()
        host, hass = self._host("EFB")
        host.stage_start_time = 900.0
        host._v2_runtime = _FixedRuntime(_analysis(now))

        with patch(
            "runtime.charge.strategy.main_authority.decide_main_transition",
            wraps=decide_main_transition,
        ) as decide:
            actions = await self._tick(host, now=now)

        self.assertEqual(decide.call_count, 1)
        self.assertEqual(
            decide.call_args.kwargs["main_elapsed_s"], main_fallback_seconds()
        )
        self.assertEqual(
            decide.call_args.kwargs["main_limit_s"], main_fallback_seconds()
        )
        self.assertEqual(
            actions["recovery_shadow"]["authority_decision"],
            {
                "action": AuthorityAction.ENTER_MIX.value,
                "reason": "main_timeout_ca_efb_v1_compatible_mix",
            },
        )
        self.assertEqual(host.current_stage, host.STAGE_MIX)
        self.assertTrue(
            actions["log_event"].startswith(
                "MIX_STARTED | reason=main_timeout_ca_efb_v1_compatible_mix"
            )
        )
        self.assertIn("set_voltage", actions)
        self.assertIn("set_current", actions)
        self.assertNotIn("turn_on", actions)
        self.assertEqual(hass.calls, [])

    async def test_prep_route_and_mix_timeout_effect_at_application_boundary(self):
        prep, prep_hass = self._host("EFB", ManagedChargeController.STAGE_PREP)
        prep_actions = await self._tick(prep, now=1000.0, voltage=12.0, current=0.6, is_cv=False)
        self.assertEqual(prep.current_stage, prep.STAGE_MAIN)
        self.assertIn("set_voltage", prep_actions)
        self.assertIn("set_current", prep_actions)
        self.assertNotIn("turn_on", prep_actions)
        self.assertEqual(prep_hass.calls, [])

        mix, mix_hass = self._host("EFB", ManagedChargeController.STAGE_MIX)
        mix._v2_target_voltage_v = 16.5
        mix.stage_start_time = 2000.0 - mix_max_active_seconds("EFB") - 1.0
        mix._v2_runtime = _FixedRuntime(_analysis(2000.0))
        actions = await self._tick(mix, now=2000.0, voltage=16.4)
        self.assertEqual(actions["recovery_shadow"]["authority_decision"]["reason"], "MIX_TIMEOUT")
        self.assertTrue(actions.get("turn_off"))
        self.assertEqual(mix.current_stage, mix.STAGE_DONE)
        self.assertNotEqual(mix.current_stage, mix.STAGE_SAFE_WAIT)
        self.assertEqual(mix_hass.calls, [])

    async def test_prep_soft_start_targets_dispatch_below_transition_threshold(self):
        prep, hass = self._host("EFB", ManagedChargeController.STAGE_PREP)
        temperature = 25.0
        expected_selected = select_prep_target(capacity_ah=prep.ah_capacity)
        expected_voltage = prep._apply_temperature_compensation(
            float(PREP_VOLTAGE_V.default), temperature
        )
        from application.production_target_policy import bound_host_target
        expected_voltage, expected_current = bound_host_target(
            prep, (expected_voltage, expected_selected.current_a), hv=False
        )

        with patch(
            "charge_controller.select_prep_target", wraps=select_prep_target
        ) as select_target, patch.object(
            prep, "_prep_target", wraps=prep._prep_target
        ) as prep_target:
            actions = await self._tick(
                prep, now=1000.0, voltage=11.5, current=0.6, is_cv=False
            )

        select_target.assert_called_once_with(capacity_ah=float(prep.ah_capacity))
        prep_target.assert_called_once_with(temperature)
        self.assertEqual(actions["set_voltage"], expected_voltage)
        self.assertEqual(actions["set_current"], expected_current)
        self.assertEqual(prep.current_stage, prep.STAGE_PREP)
        self.assertNotIn("log_event_end", actions)
        self.assertNotIn("turn_on", actions)
        self.assertEqual(hass.calls, [])

    async def test_ordinary_mix_finish_hold_decision_and_sticky_effect_at_application_boundary(self):
        now = 2000.0
        mix, hass = self._host("EFB", ManagedChargeController.STAGE_MIX)
        mix._v2_target_voltage_v = 16.5
        mix._v2_runtime = _FixedRuntime(
            _analysis(now, current=0.45, current_min=0.50, seconds_since_min=600.0),
            decision=RecoveryDecision.FINISH_STAGE,
        )
        from runtime.charge.strategy.mix import decide_mix_transition

        with patch(
            "runtime.charge.strategy.mix.decide_mix_transition",
            wraps=decide_mix_transition,
        ) as decide:
            actions = await self._tick(mix, now=now, voltage=16.4, current=0.45)

        self.assertEqual(decide.call_count, 1)
        self.assertEqual(decide.call_args.kwargs["policy_decision"], RecoveryDecision.FINISH_STAGE)
        self.assertEqual(actions["recovery_shadow"]["authority_decision"], {
            "action": AuthorityAction.START_FINISH_HOLD.value,
            "reason": "mode_specific_end_of_charge_evidence_confirmed",
        })
        self.assertEqual(mix.current_stage, mix.STAGE_MIX)
        self.assertEqual(mix.finish_timer_start, now)
        self.assertTrue(mix._delta_reported)
        self.assertEqual(mix._delta_trigger_mode, "CV")
        self.assertEqual(actions["log_event"].split(" | ")[0], "V2_FINISH_HOLD_START")
        self.assertIn("Sticky finish-hold", actions["notify"])
        self.assertNotIn("turn_off", actions)
        self.assertEqual(hass.calls, [])

    async def test_desulfation_entry_and_completion_through_production_stage_dispatch(self):
        now = 3000.0
        main, main_hass = self._host("EFB")
        main._v2_runtime = _FixedRuntime(_analysis(now))
        entry_decision = AuthorityDecision(AuthorityAction.ENTER_DESULFATION, "fixture-entry")
        with patch(
            "runtime.charge.strategy.main_authority.decide_main_transition",
            return_value=entry_decision,
        ) as decide_main:
            entry_actions = await self._tick(main, now=now)

        decide_main.assert_called_once()
        self.assertEqual(entry_actions["recovery_shadow"]["authority_decision"], {
            "action": AuthorityAction.ENTER_DESULFATION.value,
            "reason": "fixture-entry",
        })
        self.assertEqual(main.current_stage, main.STAGE_DESULFATION)
        self.assertEqual(main.antisulfate_count, 1)
        self.assertEqual(entry_actions["log_event"], "START | V2_DESULFATION")
        self.assertIn("set_voltage", entry_actions)
        self.assertIn("set_current", entry_actions)
        self.assertNotIn("turn_on", entry_actions)
        self.assertEqual(main_hass.calls, [])

        from runtime.charge.runtime.desulfation_completion import complete_desulfation_to_safe_wait
        from runtime.charge.strategy.desulfation import decide_desulfation
        from runtime.charge.strategy.desulfation_variables import desulfation_duration_seconds

        completion_now = now + desulfation_duration_seconds()
        main.stage_start_time = now
        event_order = []
        original_decide = decide_desulfation
        original_effect = complete_desulfation_to_safe_wait

        def record_decision(**kwargs):
            event_order.append("strategy")
            return original_decide(**kwargs)

        def record_effect(*args, **kwargs):
            event_order.append("effect")
            return original_effect(*args, **kwargs)

        with patch("runtime.charge.strategy.desulfation.decide_desulfation", side_effect=record_decision) as decide_desulfation_mock, patch(
            "runtime.charge.runtime.desulfation_completion.complete_desulfation_to_safe_wait",
            side_effect=record_effect,
        ) as completion_effect:
            completion_actions = await self._tick(main, now=completion_now)

        decide_desulfation_mock.assert_called_once()
        completion_effect.assert_called_once()
        self.assertEqual(event_order, ["strategy", "effect"])
        self.assertEqual(completion_actions["recovery_shadow"]["authority_decision"]["action"],
                         AuthorityAction.COMPLETE_TO_SAFE_WAIT.value)
        self.assertEqual(main.current_stage, main.STAGE_SAFE_WAIT)
        self.assertEqual(main._safe_wait_next_stage, main.STAGE_MAIN)
        self.assertEqual(main._safe_wait_start, completion_now)
        self.assertTrue(completion_actions["turn_off"])
        self.assertEqual(completion_actions["log_event"], "START | INTERMEDIATE_RECOVERY_COMPLETE")
        self.assertNotIn("turn_on", completion_actions)
        self.assertEqual(main_hass.calls, [])


if __name__ == "__main__":
    unittest.main()
