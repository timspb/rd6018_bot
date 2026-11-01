import types
import unittest
from unittest.mock import patch

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import operator_hmi as hmi
from runtime import production_runtime
from operator_managed_stop import _replace_legacy_power_toggle, _stop_exact_session
from operator_managed_stop import _stop_orphan_main_guard
from runtime_safety import OutputOffNotConfirmed


def _off_live():
    return {"switch": "off", "current": 0.0}


async def _off_live_async():
    return _off_live()


class FakeManual:
    def __init__(self, *, confirmed=True):
        self.is_active = True
        self.started_at = 123.0
        self.confirmed = confirmed
        self.stop_calls = []
        self.retired = 0

    async def stop(self, reason):
        self.stop_calls.append(reason)
        if self.confirmed:
            self.is_active = False
        return self.confirmed

    async def _retire_runner(self):
        self.retired += 1


class OperatorManagedStopTests(unittest.IsolatedAsyncioTestCase):
    async def test_orphan_main_guard_stop_requires_fresh_proof_and_retires_once(self):
        from application.operator_recovery_clearance import VerifiedOffEvidence
        from application.guard_execution_owner_lock import GuardExecutionOwnerLock
        binding = {"session_id": "S1", "battery_id": "B1", "document_sha256": "digest"}
        state = {"binding": binding, "retired": False, "valid": True}

        class Retirement:
            def __init__(self, app): self.app = app
            def orphan_binding(self): return None if state["retired"] else dict(state["binding"])
            def validate(self, candidate): return state["valid"] and candidate == state["binding"]
            def retire(self, sid, *, binding, off_evidence):
                if not self.validate(binding) or not isinstance(off_evidence, VerifiedOffEvidence): return None
                state["retired"] = True
                return types.SimpleNamespace(session_id=sid)
            def finalize(self, sid): self.app.charge_controller._guarded_restore_candidate = None

        class Port:
            def __init__(self): self._guard_owner_lock = GuardExecutionOwnerLock(); self.calls = 0
            async def request_verified_off_evidence(self):
                self.calls += 1
                return VerifiedOffEvidence("tx-1", __import__("time").monotonic())

        controller = types.SimpleNamespace(current_stage="IDLE", STAGE_IDLE="IDLE",
                                           _guarded_restore_candidate=types.SimpleNamespace(session_id="S1"))
        app = types.SimpleNamespace(charge_controller=controller, manual_session_manager=None,
                                    _hard_stop_charge=None)
        port = Port()
        with patch("operator_managed_stop._orphan_retirement", side_effect=lambda _app: Retirement(_app)), \
             patch("application.execution_port.get_or_create_execution_port", return_value=port), \
             patch("operator_managed_stop._active_session_token", return_value=None):
            token = "orphan-main:S1:B1:digest"
            ok, _ = await _stop_orphan_main_guard(app, token)
            self.assertTrue(ok)
            self.assertEqual(port.calls, 1)
            self.assertIsNone(controller._guarded_restore_candidate)
            again, _ = await _stop_orphan_main_guard(app, token)
            self.assertFalse(again)
            self.assertEqual(port.calls, 1)

    async def test_orphan_stop_rejects_stale_identity_no_native_proof_and_active_race(self):
        from application.guard_execution_owner_lock import GuardExecutionOwnerLock
        binding = {"session_id": "S1", "battery_id": "B1", "document_sha256": "digest"}
        state = {"valid": True, "changed": False}

        class Retirement:
            def orphan_binding(self):
                if state["changed"]: return {**binding, "document_sha256": "replacement"}
                return dict(binding)
            def validate(self, candidate): return state["valid"]
            def retire(self, *args, **kwargs): return None

        class Port:
            def __init__(self, proof): self._guard_owner_lock = GuardExecutionOwnerLock(); self.calls = 0; self.proof = proof
            async def request_verified_off_evidence(self):
                self.calls += 1
                if case == "identity_changed_during_off": state["valid"] = False
                return self.proof

        app = types.SimpleNamespace(charge_controller=types.SimpleNamespace(current_stage="IDLE", STAGE_IDLE="IDLE"))
        token = "orphan-main:S1:B1:digest"
        for case in ("stale", "no_proof", "active_race", "identity_changed_during_off"):
            state.update(valid=True, changed=(case == "stale"))
            port = Port(None)
            with patch("operator_managed_stop._orphan_retirement", return_value=Retirement()), \
                 patch("application.execution_port.get_or_create_execution_port", return_value=port), \
                 patch("operator_managed_stop._active_session_token", return_value="auto:race" if case == "active_race" else None):
                ok, _ = await _stop_orphan_main_guard(app, token)
                self.assertFalse(ok)
                self.assertEqual(port.calls, 0 if case in {"stale", "active_race"} else 1)

    def test_historical_power_toggle_handler_and_helper_are_retired(self):
        import inspect

        source = inspect.getsource(production_runtime)
        self.assertNotIn('F.data == "power_toggle"', source)
        self.assertNotIn("async def power_toggle_handler(", source)
        self.assertNotIn("def _legacy_power_toggle_is_disabled(", source)

    def _state(self, authority):
        return hmi.OperatorHmiState(
            process_state=hmi.HmiProcessState.RUNNING,
            authority=authority,
            title="",
            output_on=True,
            regulator="CV",
            battery_label="",
            battery_voltage_v=14.8,
            current_a=1.0,
            power_w=14.8,
            battery_temp_c=25.0,
            psu_temp_c=35.0,
            target_voltage_v=14.8,
            current_limit_a=5.0,
            progress="",
            safety="",
        )

    def test_managed_keyboard_uses_stop_only_callback_not_legacy_power_toggle(self):
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🛑 Остановить заряд", callback_data="power_toggle")],
                [InlineKeyboardButton(text="ℹ Подробнее", callback_data="operator_details")],
            ]
        )
        result = _replace_legacy_power_toggle(markup, self._state(hmi.HmiAuthority.AUTO))
        callbacks = [b.callback_data for row in result.inline_keyboard for b in row]
        self.assertIn("operator_managed_stop", callbacks)
        self.assertNotIn("power_toggle", callbacks)

    def test_nonmanaged_keyboard_does_not_rewrite_unrelated_legacy_callback(self):
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="x", callback_data="power_toggle")]]
        )
        result = _replace_legacy_power_toggle(markup, self._state(hmi.HmiAuthority.NONE))
        self.assertEqual(result.inline_keyboard[0][0].callback_data, "power_toggle")

    async def test_exact_auto_stop_uses_existing_hard_stop_and_never_toggle_path(self):
        controller = types.SimpleNamespace(
            is_active=True,
            recovery_trace_context={"session_id": "auto-1"},
            total_start_time=1.0,
        )
        calls = []

        async def hard_stop():
            calls.append("hard_stop")
            controller.is_active = False

        app = types.SimpleNamespace(
            charge_controller=controller,
            manual_session_manager=types.SimpleNamespace(is_active=False),
            _hard_stop_charge=hard_stop,
            _clear_manual_off=lambda: calls.append("clear_off"),
        )
        with patch("operator_managed_stop.log_verified_auto_stop") as record_stop:
            ok, detail = await _stop_exact_session(app, "auto:auto-1")
        record_stop.assert_called_once_with("auto:auto-1")
        self.assertTrue(ok)
        self.assertIn("Output OFF", detail)
        self.assertEqual(calls, ["hard_stop", "clear_off"])

    async def test_stale_auto_confirmation_is_non_actuating(self):
        controller = types.SimpleNamespace(
            is_active=True,
            recovery_trace_context={"session_id": "replacement"},
            total_start_time=2.0,
        )
        calls = []

        async def hard_stop():
            calls.append("hard_stop")

        app = types.SimpleNamespace(
            charge_controller=controller,
            manual_session_manager=types.SimpleNamespace(is_active=False),
            _hard_stop_charge=hard_stop,
        )
        ok, detail = await _stop_exact_session(app, "auto:old")
        self.assertFalse(ok)
        self.assertIn("изменилась", detail)
        self.assertEqual(calls, [])

    async def test_unconfirmed_off_with_readonly_off_zero_current_retires_auto_session(self):
        controller = types.SimpleNamespace(
            is_active=True,
            recovery_trace_context={"session_id": "auto-1"},
            total_start_time=1.0,
            stop_calls=[],
        )

        def stop(*, clear_session):
            controller.stop_calls.append(clear_session)
            controller.is_active = False

        controller.stop = stop

        async def hard_stop():
            raise OutputOffNotConfirmed("OFF command accepted but switch state was not confirmed")

        app = types.SimpleNamespace(
            charge_controller=controller,
            manual_session_manager=types.SimpleNamespace(is_active=False),
            _hard_stop_charge=hard_stop,
            hass=types.SimpleNamespace(
                get_all_live=_off_live_async,
            ),
        )
        ok, detail = await _stop_exact_session(app, "auto:auto-1")

        self.assertTrue(ok)
        self.assertIn("AUTO-сессия завершена программно", detail)
        self.assertIn("readback OFF", detail)
        self.assertEqual(controller.stop_calls, [True])

    async def test_unconfirmed_off_with_nonzero_current_keeps_auto_session(self):
        controller = types.SimpleNamespace(
            is_active=True,
            recovery_trace_context={"session_id": "auto-1"},
            total_start_time=1.0,
        )

        async def hard_stop():
            raise OutputOffNotConfirmed("unconfirmed")

        async def live():
            return {"switch": "off", "current": 0.20}

        app = types.SimpleNamespace(
            charge_controller=controller,
            manual_session_manager=types.SimpleNamespace(is_active=False),
            _hard_stop_charge=hard_stop,
            hass=types.SimpleNamespace(get_all_live=live),
        )
        ok, detail = await _stop_exact_session(app, "auto:auto-1")

        self.assertFalse(ok)
        self.assertIn("OutputOffNotConfirmed", detail)
        self.assertTrue(controller.is_active)

    async def test_manual_stop_retires_manual_owner_not_auto_controller(self):
        manual = FakeManual(confirmed=True)
        auto_calls = []
        app = types.SimpleNamespace(
            charge_controller=types.SimpleNamespace(is_active=False),
            manual_session_manager=manual,
            _hard_stop_charge=lambda: auto_calls.append("wrong"),
            _clear_manual_off=lambda: None,
        )
        ok, detail = await _stop_exact_session(app, "manual:123.000000")
        self.assertTrue(ok)
        self.assertIn("Output OFF", detail)
        self.assertEqual(manual.stop_calls, ["operator_stop"])
        self.assertEqual(manual.retired, 1)
        self.assertEqual(auto_calls, [])

    async def test_unconfirmed_manual_off_keeps_containment_and_does_not_retire_runner(self):
        manual = FakeManual(confirmed=False)
        app = types.SimpleNamespace(
            charge_controller=types.SimpleNamespace(is_active=False),
            manual_session_manager=manual,
        )
        ok, detail = await _stop_exact_session(app, "manual:123.000000")
        self.assertFalse(ok)
        self.assertIn("не подтверждён", detail)
        self.assertTrue(manual.is_active)
        self.assertEqual(manual.retired, 0)


if __name__ == "__main__":
    unittest.main()
