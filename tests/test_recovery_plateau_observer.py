"""Observer lifecycle and diagnostics; no hardware and no stage transitions."""
from runtime.charge.evidence.recovery_plateau_observer import RecoveryPlateauObserver
from runtime.charge.evidence.recovery_plateau_policy import PlateauVerdict


def sample(o, minute, current=.23, **overrides):
    data = dict(
        session_id="session-a", timestamp_s=minute * 60.0,
        voltage_v=14.83, current_a=current, target_voltage_v=14.82,
        is_cv=True, temp_valid=True, eligible=True,
    )
    data.update(overrides)
    return o.observe(**data)


def test_90_min_plateau_confirmed_even_below_legacy_tail_threshold():
    o=RecoveryPlateauObserver()
    results=[sample(o, m) for m in range(0, 91, 5)]
    assert results[-1].verdict == PlateauVerdict.CONFIRMED
    assert results[-1].current_drop_a == 0


def test_cv_dropout_discards_continuity():
    o=RecoveryPlateauObserver()
    for m in range(0, 91, 5):
        sample(o, m)
    assert sample(o, 95, is_cv=False).verdict == PlateauVerdict.INVALID
    assert sample(o, 100).verdict == PlateauVerdict.INVALID
    assert sample(o, 105).verdict == PlateauVerdict.OBSERVING


def test_session_change_restarts_window():
    o=RecoveryPlateauObserver()
    for m in range(0, 91, 5):
        sample(o, m)
    assert sample(o, 95, session_id="session-b").verdict == PlateauVerdict.INVALID
    assert sample(o, 100, session_id="session-b").verdict == PlateauVerdict.OBSERVING


def test_target_change_or_temperature_invalidates():
    o=RecoveryPlateauObserver()
    for m in range(0, 96, 5):
        sample(o, m)
    assert sample(o, 100, target_voltage_v=15.0).verdict == PlateauVerdict.INVALID
    assert sample(o, 105, target_voltage_v=15.0, temp_valid=False).verdict == PlateauVerdict.INVALID


def test_gap_over_10_min_starts_fresh():
    o=RecoveryPlateauObserver()
    for m in range(0, 96, 5):
        sample(o, m)
    assert sample(o, 120).verdict == PlateauVerdict.INVALID
    assert sample(o, 125).verdict == PlateauVerdict.OBSERVING


def test_non_eligible_stage_resets():
    o=RecoveryPlateauObserver()
    for m in range(0, 96, 5):
        sample(o, m)
    assert sample(o, 100, eligible=False).verdict == PlateauVerdict.INVALID
    assert sample(o, 105).verdict == PlateauVerdict.INVALID


def test_long_observation_does_not_grow_without_bound():
    o=RecoveryPlateauObserver()
    for m in range(0, 601, 5):
        sample(o, m)
    assert len(o.samples) <= 26
    assert o.samples[-1].time_s - o.samples[0].time_s <= 125*60


def test_no_non_efb_or_no_output_enables_plateau():
    o=RecoveryPlateauObserver()
    assert sample(o, 0, eligible=False).verdict == PlateauVerdict.INVALID
    assert sample(o, 5).verdict == PlateauVerdict.INVALID
