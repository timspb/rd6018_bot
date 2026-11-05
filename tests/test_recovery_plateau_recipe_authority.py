"""Candidate EFB Recovery recipe wiring; existing MAIN is the sole stage owner."""
import pytest

from recovery_policy import RecoveryDecision
from runtime.charge.decisions import AuthorityAction
from runtime.charge.evidence.first_stage import FirstStageAssessment, FirstStageState
from runtime.charge.programs.native_recipe_draft import validate_native_draft
from runtime.charge.programs.native_recipe_session import require_supported_native_execution
from runtime.charge.strategy.main_authority import decide_main_transition


def assessment(state=FirstStageState.TAIL_READY):
    return FirstStageAssessment(state, .0035, .26, .004, True, "synthetic")


def choose(state=FirstStageState.TAIL_READY, **kw):
    args = dict(
        profile="EFB", intent="recovery", first_stage=assessment(state),
        policy_decision=RecoveryDecision.CONTINUE,
        seconds_since_current_min=4 * 3600, required_tail_hold_s=3 * 3600,
        desulf_attempts=0, max_desulf_attempts=3,
        is_cv=True, current_a=.23, main_elapsed_s=1200,
        main_limit_s=72 * 3600,
    )
    args.update(kw)
    return decide_main_transition(**args)


def draft(recipe="native_efb_recovery", **overrides):
    return validate_native_draft(dict(
        schema=1, execution_kind="native_authority",
        base_recipe_id=recipe, overrides=overrides,
    ))


def test_existing_unpinned_strategy_unchanged():
    assert choose().action == AuthorityAction.ENTER_MIX


def test_adaptive_opt_in_plateau_drives_existing_intermediate_owner():
    d = choose(adaptive_recovery_enabled=True, adaptive_recovery_plateau="confirmed")
    assert d.action == AuthorityAction.ENTER_DESULFATION
    assert d.reason == "efb_adaptive_plateau_intermediate_recovery"


def test_recovery_budget_exhausted_selects_existing_final_mix():
    d = choose(adaptive_recovery_enabled=True, adaptive_recovery_plateau="confirmed",
               desulf_attempts=3)
    assert d.action == AuthorityAction.ENTER_MIX


@pytest.mark.parametrize("status", ["observing", "progressing", "invalid", "inconclusive", None])
def test_uncertain_adaptive_signal_cannot_trigger_hv(status):
    d = choose(adaptive_recovery_enabled=True, adaptive_recovery_plateau=status)
    assert d.action == AuthorityAction.CONTINUE


def test_legacy_40m_plateau_is_suppressed_only_in_opt_in_recovery():
    d = choose(FirstStageState.STUCK_PLATEAU,
               adaptive_recovery_enabled=True, adaptive_recovery_plateau="observing")
    assert d.action == AuthorityAction.CONTINUE
    old = choose(FirstStageState.STUCK_PLATEAU)
    assert old.action == AuthorityAction.ENTER_DESULFATION


def test_safety_veto_takes_precedence_over_confirmed_plateau():
    d = choose(adaptive_recovery_enabled=True, adaptive_recovery_plateau="confirmed",
               policy_decision=RecoveryDecision.PAUSE_THERMAL)
    assert d.action == AuthorityAction.STOP_AND_DIAGNOSE
    d = choose(FirstStageState.THERMALLY_UNSTABLE, adaptive_recovery_enabled=True,
               adaptive_recovery_plateau="confirmed")
    assert d.action == AuthorityAction.STOP_AND_DIAGNOSE


def test_no_adaptive_mode_on_agm_or_normal():
    for overrides in ({"profile": "AGM"}, {"intent": "normal"}):
        d = choose(adaptive_recovery_enabled=True, adaptive_recovery_plateau="confirmed",
                   **overrides)
        assert d.action != AuthorityAction.ENTER_DESULFATION


def test_recipe_values_are_validated_and_restricted():
    d = draft(**{
        "charge.recovery_plateau.enabled": 1,
        "charge.recovery_plateau.min_window_minutes": 90.,
        "charge.recovery_plateau.max_window_minutes": 120.,
    })
    require_supported_native_execution(d)
    with pytest.raises(ValueError):
        draft("native_agm_recovery", **{"charge.recovery_plateau.enabled": 1})
    with pytest.raises(ValueError):
        draft("native_efb_normal", **{"charge.recovery_plateau.enabled": 1})
    with pytest.raises(ValueError):
        draft(**{"charge.recovery_plateau.enabled": 2})
    with pytest.raises(ValueError):
        d = draft(**{
            "charge.recovery_plateau.enabled": 1,
            "charge.recovery_plateau.min_window_minutes": 125.,
            "charge.recovery_plateau.max_window_minutes": 120.,
        })
        require_supported_native_execution(d)

def test_pinned_recipe_reaches_existing_main_owner_as_immutable_values():
    from types import SimpleNamespace
    from runtime.charge.programs.native_recipe_session import (
        NativeRecipeSessionSelection, native_target_parameters, _digest,
    )
    overrides = dict(draft(**{
        "charge.recovery_plateau.enabled": 1,
        "charge.recovery_plateau.min_window_minutes": 95.,
        "charge.recovery_plateau.max_window_minutes": 120.,
        "charge.recovery_plateau.strong_plateau_drop_a": .01,
        "charge.recovery_plateau.weak_plateau_drop_a": .02,
    }).overrides)
    payload = dict(base_recipe_id="native_efb_recovery", name="recovery-plateau",
                   version=1, overrides=overrides)
    selection = NativeRecipeSessionSelection(
        name="recovery-plateau", version=1,
        base_recipe_id="native_efb_recovery", profile="EFB", intent="recovery",
        overrides=tuple(sorted(overrides.items())), content_sha256=_digest(payload),
    )
    host = SimpleNamespace(
        _native_recipe_session_selection=selection,
        battery_type="EFB", _v2_intent="recovery",
    )
    selected = native_target_parameters(host, "MAIN_POLICY")
    assert selected["adaptive_plateau_enabled"] == 1
    assert selected["min_window_minutes"] == 95.
    assert selected["max_window_minutes"] == 120.
    assert selected["strong_plateau_drop_a"] == .01
