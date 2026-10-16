"""D076: genuine, source-fresh native MIX current limitation (offline only)."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import copy
import unittest

from runtime.charge import BatteryProfile, ChargeEngine, ChemistryProfile, Measurements
from runtime.charge.strategy import (
    ChargeRecipe, ChargeStrategy, StrategyRuntimeState,
    MainPolicy, MainPolicyConfig, RecoveryPolicy, RecoveryPolicyConfig,
    CCMixExitConfig, CVMixExitConfig, MixPolicy, MixPolicyConfig,
)
from runtime.charge.strategy.mix_current_evidence import (
    CommittedMixCurrentCap, ClipStatus, MixClipEvidence, classify_mix_current_clip,
)

NOW = 1_800_000_000.0
KEYS = ("output_state_code_v2", "regulation_code",
        "set_current_readback_v2", "current")


def stamp(seconds: float = NOW - 1) -> str:
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat()


def native_live() -> dict:
    """4 genuine register/value sources with independent entity identities."""
    return {
        "output_state_code_v2": 1, "regulation_code": 1,
        "set_current_readback_v2": 0.70, "current": 0.69,
        "switch": "on", "is_cc": True,
        "_meta": {
            key: {
                "entity_id": "sensor.native_rd6018_" + key,
                "source_key": key, "status": "ok",
                "last_reported": stamp(),
            } for key in KEYS
        },
    }


def accepted() -> CommittedMixCurrentCap:
    # Simulated receipt; in production ONLY a reconciled owner can issue it.
    return CommittedMixCurrentCap(
        session_id="mix-epoch-1", battery_id="battery-EFB-70",
        chemistry="EFB", initial_ceiling_a=2.10,
        acknowledged_limit_a=0.70, acknowledged_at_epoch_s=NOW - 5,
        committed=True,
    )


def classify(live=None, receipt=None, **override):
    params = {
        "session_id": "mix-epoch-1", "battery_id": "battery-EFB-70",
        "chemistry": "EFB", "now_epoch_s": NOW,
    }
    params.update(override)
    return classify_mix_current_clip(
        native_live() if live is None else live,
        receipt=accepted() if receipt is None else receipt, **params,
    )


class NativeClipEvidenceTests(unittest.TestCase):
    def assert_unknown(self, live, receipt=None, **overrides):
        result = classify(live, receipt, **overrides)
        self.assertEqual(ClipStatus.UNKNOWN, result.status, result.reason)
        self.assertTrue(result.censor_cc_delta(adaptive_ratchet_active=True))
        self.assertFalse(result.censor_cc_delta(adaptive_ratchet_active=False))

    def test_positive_requires_lower_acknowledged_cap_and_genuine_native_cc(self):
        result = classify()
        self.assertEqual(ClipStatus.PROVED_CLIPPED, result.status)
        self.assertEqual("native_cc_at_committed_iset", result.reason)
        self.assertTrue(result.censor_cc_delta(adaptive_ratchet_active=True))

    def test_no_receipt_is_not_a_false_negative_when_ratchet_is_active(self):
        result = classify_mix_current_clip(
            native_live(), receipt=None,
            session_id="mix-epoch-1", battery_id="battery-EFB-70",
            chemistry="EFB", now_epoch_s=NOW,
        )
        self.assertEqual(ClipStatus.UNKNOWN, result.status)
        self.assertTrue(result.censor_cc_delta(adaptive_ratchet_active=True))
        self.assertFalse(result.censor_cc_delta(adaptive_ratchet_active=False))

    def test_ordinary_cc_without_a_cap_lets_ordinary_delta_continue(self):
        no_cap = MixClipEvidence(ClipStatus.UNKNOWN, "no_cap")
        self.assertFalse(no_cap.censor_cc_delta(adaptive_ratchet_active=False))

    def test_unchanged_or_uncommitted_authority_cannot_prove_clipping(self):
        for receipt in (
            replace(accepted(), committed=False),
            replace(accepted(), acknowledged_limit_a=2.10),
            replace(accepted(), acknowledged_limit_a=2.09),
            replace(accepted(), acknowledged_limit_a=float("nan")),
            replace(accepted(), acknowledged_at_epoch_s=NOW + 5),
        ):
            with self.subTest(receipt=receipt):
                self.assert_unknown(native_live(), receipt)

    def test_wrong_identity_or_chemistry_is_rejected(self):
        self.assert_unknown(native_live(), accepted(), session_id="other")
        self.assert_unknown(native_live(), accepted(), battery_id="other")
        self.assert_unknown(native_live(), replace(accepted(), chemistry="CA/CA"))
        excluded = classify(native_live(), accepted(), chemistry="AGM")
        self.assertEqual(ClipStatus.NOT_CLIPPED, excluded.status)

    def test_cv_native_register_is_not_current_limiting(self):
        live = native_live()
        live["regulation_code"] = 0
        result = classify(live)
        self.assertEqual(ClipStatus.NOT_CLIPPED, result.status)
        self.assertEqual("native_cv", result.reason)

    def test_missing_output_or_unknown_regulation_or_current_never_proves(self):
        for key, value in (
            ("output_state_code_v2", 0), ("output_state_code_v2", "unknown"),
            ("regulation_code", 2), ("regulation_code", None),
            ("current", None), ("current", -1),
            ("set_current_readback_v2", "unknown"),
            ("set_current_readback_v2", 1.5),
        ):
            with self.subTest(key=key, value=value):
                live = native_live()
                live[key] = value
                self.assert_unknown(live)

    def test_old_ui_flags_cannot_replace_genuine_registers(self):
        live = native_live()
        live["regulation_code"] = "unavailable"
        live["is_cc"] = True
        self.assert_unknown(live)
        live = native_live()
        live["output_state_code_v2"] = None
        live["switch"] = "on"
        self.assert_unknown(live)

    def test_stale_future_and_cross_epoch_modbus_heartbeats(self):
        for key in KEYS:
            for t in (NOW - 60, NOW + 5):
                with self.subTest(key=key, t=t):
                    live = native_live()
                    live["_meta"][key]["last_reported"] = stamp(t)
                    self.assert_unknown(live)
        live = native_live()
        live["_meta"]["current"]["last_reported"] = stamp(NOW - 19)
        self.assert_unknown(live)

    def test_missing_malformed_duplicated_or_aliased_native_source(self):
        for key in KEYS:
            with self.subTest(key=key):
                live = native_live()
                del live["_meta"][key]
                self.assert_unknown(live)
                live = native_live()
                live["_meta"][key]["source_key"] = "switch"
                self.assert_unknown(live)
                live = native_live()
                live["_meta"][key]["status"] = "unavailable"
                self.assert_unknown(live)
                live = native_live()
                live["_meta"][key].pop("entity_id")
                live["_meta"][key].pop("source_key")
                self.assert_unknown(live)
        live = native_live()
        live["_meta"]["current"]["entity_id"] = live["_meta"]["regulation_code"]["entity_id"]
        self.assert_unknown(live)

    def test_snapshot_from_before_committed_cap_does_not_count(self):
        live = native_live()
        for key in KEYS:
            live["_meta"][key]["last_reported"] = stamp(NOW - 4)
        self.assert_unknown(live, replace(accepted(), acknowledged_at_epoch_s=NOW - 1))

    def test_missing_live_metadata_is_unknown_not_hardware_off(self):
        live = native_live()
        del live["_meta"]
        self.assert_unknown(live)


class StrategyMixProofPropagationTests(unittest.TestCase):
    def make_engine(self):
        main = MainPolicy(MainPolicyConfig(14.8, 5.0, 0.3, 10.0, 0.4, 10.0))
        recovery = RecoveryPolicy(RecoveryPolicyConfig(2, 16.3, 1.0))
        cc = CCMixExitConfig(16.5, 0.03, 2, 7200.0, 16.5, 2.0)
        cv = CVMixExitConfig(0.4, 0.1, 2, 7200.0, 16.5, 2.0)
        mix = MixPolicy(MixPolicyConfig(10000.0, cc, cv))
        battery = BatteryProfile(ChemistryProfile.EFB, 70.0)
        strategy = ChargeStrategy(battery, ChargeRecipe(main, recovery, mix))
        return ChargeEngine(battery, strategy=strategy)

    def test_native_clipping_passes_through_engine_to_cc_delta_censor(self):
        engine = self.make_engine()
        state = StrategyRuntimeState(stage="mix")
        verdict = classify()
        first = engine.evaluate(
            state, Measurements(16.5, 0.69, 0, 0),
            mix_mode="CC", mix_clip_evidence=verdict,
            adaptive_ratchet_active=True,
        )
        self.assertEqual("MIX_CC_DELTA_CENSORED_CURRENT_LIMIT", first.reason)
        following = engine.evaluate(
            state, Measurements(16.46, 0.69, 0, 1),
            mix_mode="CC", mix_clip_evidence=verdict,
            adaptive_ratchet_active=True,
        )
        self.assertEqual("MIX_CC_DELTA_CENSORED_CURRENT_LIMIT", following.reason)
        self.assertEqual("unarmed", engine.strategy.recipe.mix.cc.state.phase)

    def test_unknown_active_ratchet_prevents_spurious_delta(self):
        engine = self.make_engine()
        state = StrategyRuntimeState(stage="mix")
        engine.evaluate(state, Measurements(16.5, 0.69, 0, 0), mix_mode="CC")
        result = engine.evaluate(
            state, Measurements(16.46, 0.69, 0, 1), mix_mode="CC",
            mix_clip_evidence=MixClipEvidence(ClipStatus.UNKNOWN, "stale"),
            adaptive_ratchet_active=True,
        )
        self.assertEqual("MIX_CC_DELTA_CENSORED_CURRENT_LIMIT", result.reason)
        no_evidence = engine.evaluate(
            state, Measurements(16.46, 0.69, 0, 2),
            mix_mode="CC", adaptive_ratchet_active=True,
        )
        self.assertEqual("MIX_CC_DELTA_CENSORED_CURRENT_LIMIT", no_evidence.reason)

    def test_no_ratchet_preserves_normal_vmax_and_delta_hold(self):
        engine = self.make_engine()
        state = StrategyRuntimeState(stage="mix")
        engine.evaluate(state, Measurements(16.5, 2, 0, 0), mix_mode="CC")
        engine.evaluate(state, Measurements(16.46, 2, 0, 1), mix_mode="CC")
        result = engine.evaluate(state, Measurements(16.46, 2, 0, 2), mix_mode="CC")
        self.assertEqual("MIX_CC_DELTA_CONFIRMED", result.reason)
        held = engine.evaluate(
            state, Measurements(16.46, 2, 0, 3),
            mix_mode="CC",
            mix_clip_evidence=MixClipEvidence(ClipStatus.UNKNOWN, "lost"),
            adaptive_ratchet_active=True,
        )
        self.assertEqual("MIX_CC_HOLD", held.reason)

    def test_adaptive_proof_is_ignored_outside_mix_phase(self):
        engine = self.make_engine()
        state = StrategyRuntimeState(stage="main")
        result = engine.evaluate(
            state, Measurements(14.8, 5, 0, 0),
            mix_clip_evidence=MixClipEvidence(ClipStatus.PROVED_CLIPPED, "mock"),
            adaptive_ratchet_active=True,
        )
        self.assertEqual("main", result.next_stage)


if __name__ == "__main__":
    unittest.main()
