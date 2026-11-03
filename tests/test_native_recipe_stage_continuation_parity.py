"""Native recipe parity across actual recovery, MIX and SAFE_WAIT stages.

Uses independent production host instances and real stage policies. No device I/O.
"""
import unittest
from unittest.mock import patch

from charge_controller import ManagedChargeController
from application.charge_stage_tick import run_charge_stage_tick
from pb_domain import ChargeIntent
from runtime.charge.programs.native_recipe_runtime import run_native_recipe_tick
from runtime.charge.strategy.recovery_safe_wait import RecoverySafeWaitContinuation
from runtime.charge.strategy.final_safe_wait import FinalSafeWaitContinuation


class _NoHardware:
    pass


def _host(profile, intent, kind, *, generation=900.0):
    host = ManagedChargeController(_NoHardware())
    host.battery_type = profile
    host.ah_capacity = 72
    host._v2_intent = ChargeIntent(intent)
    host.total_start_time = generation
    host._v2_trace_session_id = "parity-session"
    host._v2_trace_started_at = generation
    host.stage_start_time = 1000.0
    host._stage_start_ah = 1.0
    host._last_known_output_on = kind not in {"RECOVERY_SAFE_WAIT", "FINAL_SAFE_WAIT"}
    if kind == "RECOVERY_SAFE_WAIT":
        host.current_stage = host.STAGE_SAFE_WAIT
        host._recovery_safe_wait = RecoverySafeWaitContinuation(
            source_stage=host.STAGE_DESULFATION,
            next_stage=host.STAGE_MAIN, target_voltage_v=14.7,
            target_current_a=1.0, started_at=1000.0,
            session_id="parity-session", recovery_attempt=0,
            agm_stage_idx=0, session_generation=generation)
        host._safe_wait_next_stage = host.STAGE_MAIN
    elif kind == "FINAL_SAFE_WAIT":
        host.current_stage = host.STAGE_SAFE_WAIT
        host._final_safe_wait = FinalSafeWaitContinuation(
            source_stage=host.STAGE_MIX,
            next_stage=host.STAGE_DONE, target_voltage_v=13.8,
            target_current_a=1.0, started_at=1000.0,
            session_id="parity-session", completion_reason="mix_complete",
            session_generation=generation)
        host._safe_wait_next_stage = host.STAGE_DONE
    else:
        host.current_stage = getattr(host, "STAGE_" + kind)
    return host


class NativeRecipeStageContinuationParityTests(unittest.IsolatedAsyncioTestCase):
    async def test_recovery_mix_wait_and_done_multitick_parity(self):
        for profile in ("Ca/Ca", "EFB", "AGM"):
            for intent in ("normal", "recovery", "conditioning"):
                for kind in ("DESULFATION", "RECOVERY_SAFE_WAIT", "MIX",
                             "FINAL_SAFE_WAIT", "DONE"):
                    for generation in (900.0, 899.0):
                        original = _host(profile, intent, kind, generation=900.0)
                        adapted = _host(profile, intent, kind, generation=900.0)
                        if generation != 900.0:
                            # Continuation belongs to a different epoch; the
                            # production owner must reject stale re-enablement.
                            for host in (original, adapted):
                                continuation = (host._recovery_safe_wait
                                                if kind == "RECOVERY_SAFE_WAIT"
                                                else host._final_safe_wait
                                                if kind == "FINAL_SAFE_WAIT" else None)
                                if continuation is not None:
                                    from dataclasses import replace
                                    stale = replace(continuation,
                                                    session_generation=generation)
                                    if kind == "RECOVERY_SAFE_WAIT":
                                        host._recovery_safe_wait = stale
                                    else:
                                        host._final_safe_wait = stale
                        for at, voltage, output_on in (
                            (1001., 14.8, False),
                            (1010., 14.0, False),
                            (1020., 14.0, True),
                        ):
                            kwargs = dict(
                                stage_before=original.current_stage,
                                voltage=voltage, current=0.2,
                                temp_ext=25.0, is_cv=True, ah=2.0,
                                output_is_on=output_on, manual_off_active=False,
                                is_cc=False, manual_active=False,
                            )
                            with self.subTest(profile=profile,intent=intent,
                                              kind=kind,generation=generation,at=at):
                                with patch("time.time",return_value=at):
                                    with patch.object(original, "_save_session"):
                                        a = await run_charge_stage_tick(original,**kwargs)
                                    with patch.object(adapted, "_save_session"):
                                        b = await run_native_recipe_tick(
                                            f"native_{profile.lower().replace('/', '_')}_{intent}",
                                            adapted,**kwargs)
                                self.assertEqual(a,b)
                                self.assertEqual(original.current_stage,adapted.current_stage)
                                self.assertEqual(original._v2_intent,adapted._v2_intent)
                                self.assertEqual(original.stage_start_time,adapted.stage_start_time)
                                self.assertEqual(original._safe_wait_next_stage,
                                                 adapted._safe_wait_next_stage)
                                self.assertEqual(original._last_known_output_on,
                                                 adapted._last_known_output_on)

