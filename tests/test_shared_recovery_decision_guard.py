import pytest

from pb_domain import ChargeIntent
from recovery_policy import RecoveryDecision, is_unsafe_recovery_decision
from runtime.charge.decisions import AuthorityAction
from runtime.charge.evidence.first_stage import FirstStageAssessment, FirstStageState
from runtime.charge.strategy.main_authority import decide_main_transition
from runtime.charge.strategy.mix import decide_mix_transition


UNSAFE = (
    RecoveryDecision.HOLD_OUTPUT_OFF,
    RecoveryDecision.PAUSE_THERMAL,
    RecoveryDecision.REST_AND_DIAGNOSE,
)


@pytest.mark.parametrize("decision", UNSAFE)
def test_shared_guard_classifies_unsafe_recovery_decisions(decision):
    assert is_unsafe_recovery_decision(decision)


@pytest.mark.parametrize("decision", (RecoveryDecision.CONTINUE, RecoveryDecision.FINISH_STAGE))
def test_shared_guard_does_not_classify_non_unsafe_decisions(decision):
    assert not is_unsafe_recovery_decision(decision)


@pytest.mark.parametrize("decision", UNSAFE)
def test_main_authority_keeps_unsafe_policy_fail_closed(decision):
    evidence = FirstStageAssessment(
        state=FirstStageState.TAIL_READY,
        current_c_rate=0.004,
        tail_threshold_a=0.28,
        tail_threshold_c=0.004,
        near_target=True,
        reason="test",
    )
    result = decide_main_transition(
        profile="EFB",
        intent=ChargeIntent.RECOVERY,
        first_stage=evidence,
        policy_decision=decision,
        seconds_since_current_min=10_000,
        required_tail_hold_s=1,
    )
    assert result.action == AuthorityAction.STOP_AND_DIAGNOSE
    assert result.reason == f"policy_{decision.value}"


@pytest.mark.parametrize("decision", UNSAFE)
def test_mix_authority_keeps_unsafe_policy_fail_closed(decision):
    result = decide_mix_transition(
        profile="EFB",
        policy_decision=decision,
        active_elapsed_s=0,
        finish_hold_started_at=None,
        now_s=1000,
        authority_limit_s=20 * 3600,
        finish_hold_s=2 * 3600,
    )
    assert result.action == AuthorityAction.STOP_AND_DIAGNOSE
    assert result.reason == f"policy_{decision.value}"
