"""Observer lifecycle and diagnostics; no hardware and no stage transitions."""
from types import SimpleNamespace

from application.charge_session_tick import (
    _observe_efb_recovery_plateau_shadow,
    _run_charge_session_tick_body,
)
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

def _shadow_host():
    return SimpleNamespace(
        STAGE_MAIN="MAIN",
        PROFILE_EFB="EFB",
        battery_type="EFB",
        _v2_intent="recovery",
        _v2_trace_session_id="session-a",
        _recovery_plateau_observer=None,
        _recovery_plateau_latest=None,
    )


def _observe_shadow(host, actions, *, timestamp=1200.0, stage="MAIN", output=True, temperature=25.0):
    _observe_efb_recovery_plateau_shadow(
        host,
        stage_before=stage,
        timestamp_s=timestamp,
        voltage=14.83,
        current=0.23,
        temp_ext=temperature,
        target_before=14.82,
        is_cv=True,
        output_is_on=output,
        actions=actions,
    )


def test_tick_shadow_helper_emits_read_only_evidence_without_actuator_authority():
    host = _shadow_host()
    actions = {}
    _observe_shadow(host, actions, timestamp=0.0)
    _observe_shadow(host, actions, timestamp=300.0)
    shadow = actions["efb_recovery_plateau_shadow"]
    assert shadow["verdict"] == "observing"
    assert shadow["actuator_authority"] is False
    assert host._recovery_plateau_latest.verdict == PlateauVerdict.OBSERVING
    assert host._recovery_plateau_observer.samples


def test_tick_shadow_helper_preserves_eligibility_and_resets_observer():
    host = _shadow_host()
    actions = {}
    _observe_shadow(host, actions, timestamp=0.0)
    observer = host._recovery_plateau_observer
    assert observer.samples
    _observe_shadow(host, actions, timestamp=300.0, stage="MIX")
    assert actions["efb_recovery_plateau_shadow"]["verdict"] == "invalid"
    assert actions["efb_recovery_plateau_shadow"]["actuator_authority"] is False
    assert host._recovery_plateau_latest.verdict == PlateauVerdict.INVALID
    assert not observer.samples


def test_tick_shadow_helper_recipe_change_replaces_existing_observer(monkeypatch):
    import runtime.charge.programs.native_recipe_session as native_session

    configs = iter((
        {"min_window_minutes": 90.0},
        {"min_window_minutes": 95.0},
    ))
    monkeypatch.setattr(native_session, "native_target_parameters", lambda _host, _stage: next(configs))
    host = _shadow_host()
    actions = {}
    _observe_shadow(host, actions, timestamp=0.0)
    previous = host._recovery_plateau_observer
    _observe_shadow(host, actions, timestamp=300.0)
    assert host._recovery_plateau_observer is not previous
    assert not previous.samples
    assert host._recovery_plateau_observer.recipe.min_window_minutes == 95.0



def test_tick_shadow_helper_has_no_execution_or_stage_authority():
    import inspect

    source = inspect.getsource(_observe_efb_recovery_plateau_shadow)
    for forbidden in (
        "ExecutionPort",
        "program_voltage",
        "program_current",
        "turn_on",
        "set_voltage",
        "current_stage =",
    ):
        assert forbidden not in source


def test_tick_shadow_helper_failure_is_invalid_and_has_no_authority(monkeypatch):
    import runtime.charge.programs.native_recipe_session as native_session

    monkeypatch.setattr(
        native_session, "native_target_parameters",
        lambda _host, _stage: (_ for _ in ()).throw(RuntimeError("recipe unavailable")),
    )
    host = _shadow_host()
    actions = {}
    _observe_shadow(host, actions)
    assert host._recovery_plateau_latest is None
    assert actions["efb_recovery_plateau_shadow"] == {
        "verdict": "invalid",
        "reason": "observer_error",
        "actuator_authority": False,
    }


def test_tick_body_retains_core_observation_authority_trace_and_persistence_phases():
    import inspect

    source = inspect.getsource(_run_charge_session_tick_body)
    required = (
        "runtime.observe(",
        "log_analysis_events(",
        "build_signal_context(",
        "host._main_sample_evidence.assess(",
        "apply_continuous_tail_hold(",
        "_observe_efb_recovery_plateau_shadow(",
        "authority_decision = apply_charge_stage_authority(",
        "build_trace_point_metadata(",
        "build_shadow_metadata(",
        "apply_stop_and_diagnose(",
        "host._log_stage_transition(",
        "host._save_session(",
    )
    for token in required:
        assert token in source, f"core tick phase missing: {token}"
    assert source.index("_observe_efb_recovery_plateau_shadow(") < source.index(
        "authority_decision = apply_charge_stage_authority("
    )
    assert source.index("authority_decision = apply_charge_stage_authority(") < source.index(
        "build_trace_point_metadata("
    )
