"""Test setup helper for the migrated final SAFE_WAIT entry effect."""

from runtime.charge.runtime.final_safe_wait_entry import (
    FinalSafeWaitEntryInput,
    apply_final_safe_wait_entry,
)


def enter_final_safe_wait(controller, *, actions, now, voltage, current, temp, ah, reason):
    target_v, target_i = controller._storage_target()
    value = FinalSafeWaitEntryInput(
        source_stage=controller.current_stage,
        safe_wait_stage=controller.STAGE_SAFE_WAIT,
        next_stage=controller.STAGE_DONE,
        session_id=controller._v2_trace_session_id,
        session_generation=controller._v2_trace_started_at,
        target_voltage_v=target_v,
        target_current_a=target_i,
        now_s=now,
        voltage_v=voltage,
        current_a=current,
        temperature_c=temp,
        ah=ah,
        reason=reason,
        log_event_end=controller._make_log_event_end(
            now, ah, voltage, current, temp, reason
        ),
    )
    if not apply_final_safe_wait_entry(controller, value, actions):
        raise AssertionError("final SAFE_WAIT test setup identity rejected")
