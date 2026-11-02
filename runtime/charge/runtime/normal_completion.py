"""Terminal completion for NORMAL charge: no MIX, recovery or storage."""
from __future__ import annotations

import logging

from runtime.charge.terminal_intent import (
    DONE_COMPLETION_TERMINAL, DONE_OUTPUT_OFF, TerminalPersistenceRequest,
)

logger = logging.getLogger("rd6018.charge.normal")


def complete_normal_charge(host, *, actions, now, voltage, current, temp, ah, reason):
    """Record normal completion and request verified OFF through existing executor."""
    previous_stage = host.current_stage
    elapsed = max(0.0, now - host.stage_start_time)
    stage_ah = max(0.0, ah - host._stage_start_ah)
    host._recovery_safe_wait = None
    host._final_safe_wait = None
    host.current_stage = host.STAGE_DONE
    host._clear_restored_targets()
    host.stage_start_time = now
    host._stage_start_ah = ah
    host.finish_timer_start = None
    host._main_sample_evidence.reset()
    actions.update({
        "turn_off": True,
        "notify": "<b>✅ Стандартный заряд завершён.</b> Выход выключается, MIX не запускается.",
        "log_event": "NORMAL_CHARGE_COMPLETE",
        "log_event_end": {
            "stage": previous_stage, "v": voltage, "i": current,
            "t": temp, "ah": ah, "time_sec": elapsed,
            "ah_on_stage": stage_ah, "trigger": reason,
        },
    })
    host._save_session(
        voltage, current, ah,
        terminal_request=TerminalPersistenceRequest(
            DONE_COMPLETION_TERMINAL, DONE_OUTPUT_OFF, voltage, current, ah,
        ),
    )
    logger.info("Normal charge complete: %s -> Done | %s", previous_stage, reason)
