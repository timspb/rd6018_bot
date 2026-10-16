"""D076 native MIX current-cap evidence, no device I/O."""
from dataclasses import replace
from datetime import datetime, timezone
import unittest

from runtime.charge import BatteryProfile, ChargeEngine, ChemistryProfile, Measurements
from runtime.charge.strategy import (
    CCMixExitConfig, CVMixExitConfig, ChargeRecipe, ChargeStrategy,
    MainPolicy, MainPolicyConfig, MixPolicy, MixPolicyConfig,
    RecoveryPolicy, RecoveryPolicyConfig, StrategyRuntimeState,
)
from runtime.charge.strategy.mix_current_evidence import (
    ClipStatus, CommittedMixCurrentCap, classify_mix_current_clip,
)

NOW = 1_780_000_000.0
KEYS = ("output_state_code_v2", "regulation_code",
        "set_current_readback_v2", "current")


def iso(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat()


def snapshot():
    live = dict(
        output_state_code_v2=1,
        regulation_code=1,
        set_current_readback_v2=0.8,
        current=0.79,
        switch="off",  # misleading legacy/UI state must never win
        is_cc=False,
    )
    live["_meta"] = {
        k: {"status": "ok", "source_key": k, "last_reported": iso(NOW - 2.0)}
        for k in KEYS
    }
    return live


def receipt():
    return CommittedMixCurrentCap(
        "session-1", "battery-1", "EFB", 2.1, 0.8,
        NOW - 5.0, True,
    )


def classify(live=None, cap=None, **kw):
    params = dict(
        live=snapshot() if live is None else live,
        receipt=receipt() if cap is None else cap,
        session_id="session-1", battery_id="battery-1",
        chemistry="EFB", now_epoch_s=NOW,
        previous_report_epoch_s=NOW - 4.0,
    )
    params.update(kw)
    return classify_mix_current_clip(**params)


class MixNativeClipEvidenceTests(unittest.TestCase):
    def test_positively_committed_fresh_native_cc_at_lower_cap(self):
        value = classify()
        self.assertEqual(ClipStatus.PROVED_CLIPPED, value.status)
        self.assertTrue(value.censor_cc_delta(adaptive_ratchet_active=True))
        self.assertFalse(value.status is ClipStatus.UNKNOWN)

    def test_no_adaptive_authority_preserves_ordinary_cc_delta(self):
        value = classify_mix_current_clip(
            snapshot(), receipt=None, session_id="session-1",
            battery_id="battery-1", chemistry="EFB", now_epoch_s=NOW,
        )
        self.assertEqual(ClipStatus.UNKNOWN, value.status)
        self.assertFalse(value.censor_cc_delta(adaptive_ratchet_active=False))
        self.assertTrue(value.censor_cc_delta(adaptive_ratchet_active=True))

    def test_explicit_native_cv_is_not_current_clipped(self):
        live = snapshot()
        live["regulation_code"] = 0
        self.assertEqual(ClipStatus.NOT_CLIPPED, classify(live).status)

    def test_pending_uncommitted_or_untightened_cap_cannot_prove(self):
        for cap in (
            replace(receipt(), committed=False),
            replace(receipt(), acknowledged_limit_a=2.1),
            replace(receipt(), acknowledged_limit_a=2.099),
            replace(receipt(), initial_ceiling_a=0.0),
            replace(receipt(), acknowledged_limit_a=-0.3),
        ):
            with self.subTest(cap=cap):
                self.assertEqual(ClipStatus.UNKNOWN, classify(cap=cap).status)

    def test_wrong_session_battery_chemistry_or_agm(self):
        for override in (
            {"session_id": "other"},
            {"battery_id": "other"},
            {"chemistry": "CA/CA"},
        ):
            with self.subTest(override=override):
                self.assertEqual(ClipStatus.UNKNOWN, classify(**override).status)
        self.assertEqual(ClipStatus.NOT_CLIPPED, classify(chemistry="AGM").status)

    def test_missing_or_replayed_heartbeat_cursor_does_not_confirm_clip(self):
        self.assertEqual(ClipStatus.UNKNOWN, classify(previous_report_epoch_s=None).status)
        self.assertEqual(ClipStatus.UNKNOWN, classify(previous_report_epoch_s=NOW - 2.0).status)
        self.assertEqual(ClipStatus.UNKNOWN, classify(previous_report_epoch_s=NOW + 1.0).status)
        self.assertEqual(ClipStatus.PROVED_CLIPPED, classify(previous_report_epoch_s=NOW - 3.0).status)

    def test_no_native_metadata_or_legacy_alias_cannot_prove(self):
        self.assertEqual(
            ClipStatus.UNKNOWN, classify(live={"is_cc": True, "switch": "on"}).status,
        )
        live = snapshot()
        live["_meta"]["regulation_code"]["source_key"] = "is_cc"
        self.assertEqual(ClipStatus.UNKNOWN, classify(live).status)
        live = snapshot()
        live["_meta"]["set_current_readback_v2"]["status"] = "unavailable"
        self.assertEqual(ClipStatus.UNKNOWN, classify(live).status)

    def test_native_metadata_must_identify_distinct_producers(self):
        live = snapshot()
        for key in KEYS:
            live["_meta"][key]["entity_id"] = "sensor." + key
            live["_meta"][key].pop("source_key")
        self.assertEqual(ClipStatus.PROVED_CLIPPED, classify(live).status)
        live["_meta"]["regulation_code"]["entity_id"] = live["_meta"]["current"]["entity_id"]
        self.assertEqual(ClipStatus.UNKNOWN, classify(live).status)
        live = snapshot()
        live["_meta"]["regulation_code"].pop("source_key")
        self.assertEqual(ClipStatus.UNKNOWN, classify(live).status)

    def test_stale_skewed_missing_future_and_precommit_registers(self):
        def stale(live):
            live["_meta"]["regulation_code"]["last_reported"] = iso(NOW - 30)
        def skew(live):
            live["_meta"]["regulation_code"]["last_reported"] = iso(NOW - 18)
        def absent(live):
            live["_meta"]["set_current_readback_v2"].pop("last_reported")
        def future(live):
            live["_meta"]["current"]["last_reported"] = iso(NOW + 20)
        def precommit(live):
            for k in KEYS:
                live["_meta"][k]["last_reported"] = iso(NOW - 10)
        for mutate in (stale, skew, absent, future, precommit):
            with self.subTest(case=mutate.__name__):
                live = snapshot()
                mutate(live)
                self.assertEqual(ClipStatus.UNKNOWN, classify(live).status)

    def test_current_register_and_output_faults_cannot_prove(self):
        for key, bad in (
            ("output_state_code_v2", 0),
            ("output_state_code_v2", True),
            ("regulation_code", 7),
            ("regulation_code", True),
            ("set_current_readback_v2", 1.2),
            ("set_current_readback_v2", None),
            ("current", None),
            ("current", -1),
            ("current", 0),
        ):
            with self.subTest(key=key, bad=bad):
                live = snapshot()
                live[key] = bad
                self.assertEqual(ClipStatus.UNKNOWN, classify(live).status)

    def test_unknown_ratchet_state_censors_without_physical_intervention(self):
        live = snapshot()
        live["_meta"]["regulation_code"]["last_reported"] = iso(NOW - 45)
        evidence = classify(live)
        self.assertEqual(ClipStatus.UNKNOWN, evidence.status)
        self.assertTrue(evidence.censor_cc_delta(adaptive_ratchet_active=True))
        self.assertFalse(evidence.censor_cc_delta(adaptive_ratchet_active=False))

    def test_native_current_measured_does_not_define_arbitrary_trip_floor(self):
        live = snapshot()
        live["current"] = 0.75
        self.assertEqual(ClipStatus.PROVED_CLIPPED, classify(live).status)


class MixClipStrategyPropagationTests(unittest.TestCase):
    def make_strategy(self):
        main = MainPolicy(MainPolicyConfig(14.8, 5.0, 0.3, 10.0, 0.4, 10.0))
        rec = RecoveryPolicy(RecoveryPolicyConfig(2, 16.3, 1.0))
        cc = CCMixExitConfig(16.5, 0.03, 2, 7200.0, 16.5, 2.0)
        cv = CVMixExitConfig(0.4, 0.1, 2, 7200.0, 16.5, 2.0)
        mix = MixPolicy(MixPolicyConfig(12000.0, cc, cv))
        battery = BatteryProfile(ChemistryProfile.EFB, 70.0)
        return ChargeStrategy(battery, ChargeRecipe(main, rec, mix)), battery

    def test_charge_strategy_censors_native_adaptive_clip_then_restores_unclipped_vmax(self):
        strategy, _ = self.make_strategy()
        state = StrategyRuntimeState(stage="mix")
        evidence = classify()
        flag = evidence.censor_cc_delta(adaptive_ratchet_active=True)
        first = strategy.evaluate(state, Measurements(16.5, 0.8, None, 0.0),
                                  mix_mode="CC", current_limit_clipped=flag)
        self.assertEqual("MIX_CC_DELTA_CENSORED_CURRENT_LIMIT", first.reason)
        second = strategy.evaluate(state, Measurements(16.46, 0.8, None, 1.0),
                                   mix_mode="CC", current_limit_clipped=flag)
        self.assertEqual("MIX_CC_DELTA_CENSORED_CURRENT_LIMIT", second.reason)
        self.assertEqual(
            "MIX_CC_WAIT_VMAX",
            strategy.evaluate(state, Measurements(16.46, 0.8, None, 2.0), mix_mode="CC").reason,
        )
        strategy.evaluate(state, Measurements(16.5, 0.8, None, 3.0), mix_mode="CC")
        strategy.evaluate(state, Measurements(16.46, 0.8, None, 4.0), mix_mode="CC")
        held = strategy.evaluate(state, Measurements(16.46, 0.8, None, 5.0), mix_mode="CC")
        self.assertEqual("MIX_CC_DELTA_CONFIRMED", held.reason)
        self.assertEqual(
            "MIX_CC_HOLD",
            strategy.evaluate(state, Measurements(16.45, 0.8, None, 6.0),
                              mix_mode="CC", current_limit_clipped=True).reason,
        )
        self.assertTrue(
            strategy.evaluate(state, Measurements(16.45, 0.8, None, 7205.0),
                              mix_mode="CC", current_limit_clipped=True).completed
        )

    def test_charge_engine_forwards_mix_mode_and_clip_without_actuating(self):
        strategy, battery = self.make_strategy()
        engine = ChargeEngine(battery, strategy=strategy)
        state = StrategyRuntimeState(stage="mix")
        first = engine.evaluate(state, Measurements(16.5, 0.8, None, 0.0),
                                mix_mode="CC", current_limit_clipped=True)
        self.assertEqual("MIX_CC_DELTA_CENSORED_CURRENT_LIMIT", first.reason)


if __name__ == "__main__":
    unittest.main()
