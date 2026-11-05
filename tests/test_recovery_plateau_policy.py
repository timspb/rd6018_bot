"""Shadow-only policy tests; no hardware or production stage changes."""
from runtime.charge.evidence.recovery_plateau_policy import (
    PlateauRecipe, PlateauSample, PlateauVerdict, observe_recovery_plateau,
)


def series(minutes=120, start=0.24, end=None, interval=5, cv=True, temp_ok=True):
    end = start if end is None else end
    return [
        PlateauSample(
            time_s=m * 60,
            current_a=start + (end - start) * m / minutes,
            voltage_v=14.83,
            cv=cv,
            temp_ok=temp_ok,
        )
        for m in range(0, minutes + 1, interval)
    ]


def evaluate(minutes, **kw):
    return observe_recovery_plateau(series(minutes, **kw), target_voltage_v=14.82)


def test_minimum_window_is_90_minutes():
    assert evaluate(85).verdict == PlateauVerdict.OBSERVING
    assert evaluate(90).verdict == PlateauVerdict.CONFIRMED


def test_below_legacy_0004c_still_detects_plateau():
    assert evaluate(95, start=0.23).verdict == PlateauVerdict.CONFIRMED


def test_real_current_decline_is_progress_not_plateau():
    assert evaluate(90, start=0.40, end=0.35).verdict == PlateauVerdict.PROGRESSING


def test_ambiguous_decline_extends_to_120_without_forcing_confirmation():
    assert evaluate(90, start=0.30, end=0.285).verdict == PlateauVerdict.OBSERVING
    assert evaluate(120, start=0.30, end=0.285).verdict == PlateauVerdict.INCONCLUSIVE


def test_temperature_and_cv_are_required():
    assert evaluate(120, temp_ok=False).verdict == PlateauVerdict.INVALID
    assert evaluate(120, cv=False).verdict == PlateauVerdict.INVALID


def test_gaps_are_not_silently_counted_as_observation():
    samples = series(120)
    samples = samples[:4] + samples[8:]
    assert observe_recovery_plateau(samples, target_voltage_v=14.82).verdict == PlateauVerdict.INVALID


def test_no_backdating_to_partial_cv_window():
    samples = series(120)
    assert observe_recovery_plateau(samples[6:], target_voltage_v=14.82).verdict == PlateauVerdict.CONFIRMED
    assert observe_recovery_plateau(samples[12:], target_voltage_v=14.82).verdict == PlateauVerdict.OBSERVING


def test_recipe_validates_window_and_noise_bounds():
    import pytest
    with pytest.raises(ValueError):
        PlateauRecipe(min_window_minutes=120, max_window_minutes=90)
    with pytest.raises(ValueError):
        PlateauRecipe(strong_plateau_drop_a=0.03, weak_plateau_drop_a=0.02)
