"""Dxxx guarded EFB Storage bug reproduced on disposable session only.

No ESP, HA, Modbus, Output or production filesystem access.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from production_controller import create_production_charge_host
from runtime.charge.strategy.main_current_guard import MainCurrentGuard
from runtime.charge.strategy.main_guard_session import (
    GuardJournalError, GUARD_KEY, attach_guard, read_guard,
)
from tests.d123_final_safe_wait_helpers import enter_final_safe_wait
from runtime.charge.persistence import managed_storage_ownership_proven


class GuardedStorageTerminalTests(unittest.TestCase):
    def test_efb_main_guard_to_verified_storage_preserves_sealed_guard(self):
        with tempfile.TemporaryDirectory() as d:
            session_file = str(Path(d) / "charge_session.json")
            host = create_production_charge_host(object())
            with patch("runtime.charge.persistence.SESSION_FILE", session_file), patch(
                "charge_controller.SESSION_FILE", session_file
            ):
                host.start("EFB", 72)
                host._v2_trace_session_id = host._v2_trace_session_id or "fixture"
                host._v2_battery_id = host._v2_battery_id or "fixture-battery"
                host._main_current_guard = MainCurrentGuard.start(
                    session_id=host._v2_trace_session_id,
                    battery_id=host._v2_battery_id,
                    segment_id="fixture-main",
                    capacity_ah=72,
                    recipe_initial_current_a=7.2,
                )
                host.current_stage = host.STAGE_MAIN
                host._save_session(14.7, 1.0, 1.0)
                host.current_stage = host.STAGE_MIX
                host._save_session(16.5, 1.8, 2.0)
                enter_final_safe_wait(
                    host, actions={}, now=1000.0, voltage=16.2,
                    current=0.5, temp=25.0, ah=2.0,
                    reason="confirmed_delta_finish_hold_complete",
                )
                host._save_session(16.2, 0.0, 2.0)
                before = json.loads(Path(session_file).read_text())
                self.assertEqual(before["stage"], host.STAGE_SAFE_WAIT)
                self.assertIn(GUARD_KEY, before)
                continuation = host._final_safe_wait
                token = {
                    "kind": "final_safe_wait_to_done",
                    "session_id": continuation.session_id,
                    "session_generation": continuation.session_generation,
                    "started_at": continuation.started_at,
                    "reason": "threshold",
                }
                committed = host.commit_verified_enable_transition(
                    token, now=1010.0, voltage=13.3, current=0.0, ah=2.0,
                )
                after = json.loads(Path(session_file).read_text())
                self.assertEqual(host.current_stage, host.STAGE_DONE)
                self.assertIsNotNone(committed)
                self.assertEqual(after["stage"], host.STAGE_DONE)
                self.assertEqual(after["completion_kind"], "storage")
                self.assertEqual(after["output_intent"], "on")
                self.assertEqual(after["terminal_session_id"], host._v2_trace_session_id)
                self.assertIn(GUARD_KEY, after)
                self.assertGreater(
                    after[GUARD_KEY]["revision"], before[GUARD_KEY]["revision"]
                )
                guard, revision = read_guard(
                    after,
                    session_id=host._v2_trace_session_id,
                    battery_id=host._v2_battery_id, now_s=1011.0,
                )
                self.assertIsNone(guard.pending)
                self.assertEqual(revision, after[GUARD_KEY]["revision"])
                self.assertTrue(managed_storage_ownership_proven(host, session_file=session_file))

                # Safety ownership must see durable Storage even though Done
                # is not a ticking charge stage; a tampered disk file must
                # immediately revoke that recognition without any hardware I/O.
                from runtime.safety.managed_guard import ManagedRuntimeSafetyGuard
                from tests.test_foreign_output_ownership_grace import FakeHass, _foreign_live
                app = SimpleNamespace(
                    hass=FakeHass(_foreign_live()), charge_controller=host,
                    manual_session_manager=None, _charge_notify=lambda *a, **k: None,
                )
                safety = ManagedRuntimeSafetyGuard(app)
                with patch("runtime.charge.persistence.SESSION_FILE", session_file):
                    self.assertFalse(host.is_active)
                    self.assertTrue(safety.controller_active)
                    Path(session_file).write_text(
                        json.dumps(dict(after, output_intent="off")), encoding="utf-8",
                    )
                    self.assertFalse(safety.controller_active)
                    Path(session_file).write_text(json.dumps(after), encoding="utf-8")
                    self.assertTrue(safety.controller_active)

                altered = dict(after, output_intent="off")
                self.assertFalse(managed_storage_ownership_proven(host, document=altered))
                altered = dict(after, terminal_session_id="foreign")
                self.assertFalse(managed_storage_ownership_proven(host, document=altered))
                altered = dict(after, stage=host.STAGE_SAFE_WAIT)
                self.assertFalse(managed_storage_ownership_proven(host, document=altered))

    def test_done_cannot_mint_guard_or_accept_unverified_terminal_intent(self):
        guard = MainCurrentGuard.start(
            session_id="sid", battery_id="bid", segment_id="main",
            capacity_ah=72, recipe_initial_current_a=7.2,
        )
        base = {
            "v2_trace_session_id": "sid", "v2_battery_id": "bid",
            "stage": "Done", "profile": "EFB", "ah_limit": 72,
            "terminal_session_id": "sid", "done_state_version": 1,
            "completion_kind": "storage", "output_intent": "on",
        }
        with self.assertRaises(GuardJournalError):
            attach_guard(base, guard, now_s=3, expected_revision=0)
        for bad in (
            {"terminal_session_id": "foreign"},
            {"output_intent": "unknown"},
            {"completion_kind": "other"},
            {"done_state_version": 0},
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(GuardJournalError):
                    attach_guard(dict(base, **bad), guard, now_s=3, expected_revision=0)


if __name__ == "__main__":
    unittest.main()
