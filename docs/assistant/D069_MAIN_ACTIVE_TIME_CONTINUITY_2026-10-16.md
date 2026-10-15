# D069 — bounded active-MAIN observation continuity

Status: source-only, no hardware activation or node104 deployment.

MAIN Current Guard previously added the *entire* wall-clock interval between two fresh Output ON samples, even if the interval was 30-60 minutes with no intervening telemetry. Thus an unknown cooling/OFF/communications episode could count toward the next current step.

This source fix bounds accrual to consecutive trusted MAIN/Output ON/current samples separated by at most MAX_CONTINUOUS_SAMPLE_GAP_S = 90 seconds. The value derives from the existing ~30-second data_logger cadence, allowing up to three polling intervals as a **provisional observational bound**. Missing/stale samples and gaps beyond this bound add zero active time; the acknowledged monotone current ceiling remains intact, including after restart, OFF and desulfation. This does not claim that two ON samples prove every millisecond between them; a future owner-owned output epoch/heartbeat may strengthen the evidence.

Tests now exercise continuous 30-second sequences instead of incorrectly treating observations at t=0 and t=1800 as demonstrated 30 minutes of active MAIN. They cover long gaps, exactly 90 versus 91 seconds, duplicate timestamps, cooling OFF, desulfation pauses, stale telemetry, and persistent lower bounds with readback ACK. No recipe voltage, AGM, MIX thermal threshold or physical safety change.

Next gate: connect verified active-main clock and producer-freshness to the sole runtime owner, implement app-wide locked persistence/output sequencing and fail-closed resume-before-ON; no physical test above 15.5V. D061 adopted-child SIGKILL and D063 physical EFB/Ca/Ca SAFE_WAIT remain separate OPEN items.
