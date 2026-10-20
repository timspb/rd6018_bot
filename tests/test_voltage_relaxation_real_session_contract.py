"""Production serializer -> optional D063 observer compatibility (offline only).

Uses the real ManagedChargeController persistence and transition implementation,
not a hand-authored session mock. No HA, Modbus, ESPHome or node104 connections.
"""
import asyncio
import json
import tempfile
import time
from pathlib import Path
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

import aiosqlite

import charge_controller
from d123_final_safe_wait_helpers import enter_final_safe_wait

from charge_controller import ManagedChargeController
from tools.voltage_relaxation_sidecar import PassiveCollector, read_session


def output_off_live(voltage=13.21):
    return {
        "switch": "off", "current": 0.0, "battery_voltage": voltage, "temp_ext": 22.0,
        "_meta": {
            key: {"status": "ok", "age_s": 1.0}
            for key in ("switch", "current", "battery_voltage")
        },
    }


class ActualPersistenceContractTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.session = Path(self.tmp.name) / "charge_session.json"
        self.db = await aiosqlite.connect(":memory:")
        self.addAsyncCleanup(self.db.close)
        self.ha = AsyncMock()
        self.ha.get_all_live.return_value = output_off_live()

    def authentic_session(self, profile, *, kind="final"):
        now = time.time()
        controller = ManagedChargeController(
            None, battery_id="offline-battery-no-hardware"
        )
        controller.battery_type = profile
        controller.ah_capacity = 60
        controller._v2_trace_session_id = "real-persistence-contract-" + profile
        controller._v2_trace_started_at = now - 3600
        controller.total_start_time = now - 3600
        controller.current_stage = (
            controller.STAGE_MIX if kind == "final"
            else controller.STAGE_DESULFATION
        )
        controller.stage_start_time = now - 600
        controller._stage_start_ah = 5.0
        controller.antisulfate_count = 1
        actions = {}
        with patch.object(charge_controller, "SESSION_FILE", str(self.session)):
            if kind == "final":
                enter_final_safe_wait(controller,
                    actions=actions, now=now-45, voltage=13.5,
                    current=0.01, temp=22.0, ah=12.0, reason="offline-test",
                )
            else:
                controller.stage_start_time = now - 7200
                controller._apply_stage_authority(
                    record=None, first_stage=None, stage_before=controller.STAGE_DESULFATION,
                    timestamp_s=now, voltage=13.5, current=0.01, temp=22.0, ah=12.0,
                    is_cv=False, is_cc=True, actions=actions,
                )
            controller._save_session(13.5, 0.01, 12.0)
        assert actions.get("turn_off") is True  # intent only, NEVER executed
        saved = json.loads(self.session.read_text(encoding="utf-8"))
        return saved, read_session(self.session, now_s=time.time())

    async def _rows(self):
        cursor = await self.db.execute(
            "SELECT session_id,profile,continuation,status "
            "FROM voltage_relaxation_runs"
        )
        runs = await cursor.fetchall()
        cursor = await self.db.execute(
            "SELECT battery_voltage_v, battery_current_a "
            "FROM voltage_relaxation_samples"
        )
        return runs, await cursor.fetchall()

    async def test_efb_final_real_serializer_to_sqlite(self):
        raw, state = self.authentic_session("EFB")
        self.assertEqual(raw["stage"], "Безопасное ожидание")
        self.assertEqual(raw["safe_wait_next_stage"], "Done")
        self.assertEqual(state["continuation"], "DONE")
        self.assertEqual(state["session_id"], raw["v2_trace_session_id"])
        result = await PassiveCollector(
            session_file=self.session
        ).poll(self.db, self.ha, now_s=time.time())
        self.assertEqual(result["status"], "sample_written")
        runs, samples = await self._rows()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0][1:3], ("EFB", "DONE"))
        self.assertEqual(samples, [(13.21, 0.0)])

    async def test_calcium_recovery_real_serializer_to_sqlite(self):
        raw, state = self.authentic_session("Ca/Ca", kind="recovery")
        self.assertEqual(raw["safe_wait_next_stage"], "Main Charge")
        self.assertEqual(state["continuation"], "MAIN")
        result = await PassiveCollector(
            session_file=self.session
        ).poll(self.db, self.ha, now_s=time.time())
        self.assertEqual(result["status"], "sample_written")
        runs, samples = await self._rows()
        self.assertEqual(runs[0][1:3], ("CA/CA", "MAIN"))
        self.assertEqual(len(samples), 1)

    async def test_agm_real_serializer_never_eligible(self):
        raw, state = self.authentic_session("AGM")
        self.assertEqual(raw["profile"], "AGM")
        self.assertIsNone(state)
        result = await PassiveCollector(
            session_file=self.session
        ).poll(self.db, self.ha, now_s=time.time())
        self.assertEqual(result["status"], "no_eligible_safe_wait")
        self.ha.get_all_live.assert_not_awaited()
        runs, samples = await self._rows()
        self.assertFalse(runs)
        self.assertFalse(samples)

    async def test_production_serialized_session_cannot_override_output_on(self):
        self.authentic_session("EFB")
        self.ha.get_all_live.return_value["switch"] = "on"
        result = await PassiveCollector(
            session_file=self.session
        ).poll(self.db, self.ha, now_s=time.time())
        self.assertEqual(result["status"], "no_fresh_off_evidence")
        runs, samples = await self._rows()
        self.assertFalse(runs)
        self.assertFalse(samples)
