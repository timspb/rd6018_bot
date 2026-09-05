import unittest

from battery_registry import RecoveryCycleEvidence
from pb_domain import BatteryCondition, ChargeIntent
from recovery_trends import (
    RecoveryConfidence,
    RecoveryStatus,
    analyze_recovery_trend,
)


def cycle(
    n,
    *,
    capacity,
    cca,
    ri,
    main_imin=0.3,
    hv_imin=0.7,
    temp=30.0,
    dtemp=0.03,
):
    return RecoveryCycleEvidence(
        battery_id="b1",
        started_at=float(n * 100),
        completed_at=float(n * 100 + 50),
        intent=ChargeIntent.RECOVERY,
        condition_before=BatteryCondition.REHYDRATED,
        measured_capacity_ah=capacity,
        cca_a=cca,
        internal_resistance_mohm=ri,
        main_imin_a=main_imin,
        hv_imin_a=hv_imin,
        temp_max_c=temp,
        max_dtemp_c_per_min=dtemp,
    )


class RecoveryTrendTests(unittest.TestCase):
    def test_capacity_cca_and_ri_improvement_yields_high_confidence(self):
        trend = analyze_recovery_trend(
            [
                cycle(1, capacity=52, cca=510, ri=8.1),
                cycle(2, capacity=67, cca=590, ri=6.4),
                cycle(3, capacity=78, cca=655, ri=5.5),
            ]
        )
        self.assertEqual(trend.status, RecoveryStatus.IMPROVING)
        self.assertEqual(trend.confidence, RecoveryConfidence.HIGH)
        self.assertGreater(trend.score, 0)

    def test_imin_is_evidence_not_health_score(self):
        trend = analyze_recovery_trend(
            [
                cycle(1, capacity=70, cca=600, ri=6.0, main_imin=0.50, hv_imin=0.40),
                cycle(2, capacity=70, cca=600, ri=6.0, main_imin=0.20, hv_imin=1.20),
            ]
        )
        imin_metrics = [m for m in trend.metrics if "Imin" in m.name]
        self.assertTrue(imin_metrics)
        self.assertTrue(all(m.score == 0 for m in imin_metrics))
        self.assertEqual(trend.status, RecoveryStatus.STABLE)

    def test_thermal_instability_can_make_latest_cycle_regressing(self):
        trend = analyze_recovery_trend(
            [
                cycle(1, capacity=70, cca=600, ri=6.0),
                cycle(2, capacity=71, cca=605, ri=5.9, temp=42.0, dtemp=0.30),
            ]
        )
        self.assertEqual(trend.status, RecoveryStatus.REGRESSING)
        self.assertLess(trend.score, 0)

    def test_one_cycle_is_insufficient(self):
        trend = analyze_recovery_trend(
            [cycle(1, capacity=70, cca=600, ri=6.0)]
        )
        self.assertEqual(trend.status, RecoveryStatus.INSUFFICIENT_DATA)


if __name__ == "__main__":
    unittest.main()
