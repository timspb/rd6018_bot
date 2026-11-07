# RD6018 — UI evidence: V2 telemetry/readback warnings after MAIN → MIX

Observed in operator-supplied Telegram screenshot (received 2026-11-08). **Historical UI evidence only, not fresh ESP Native readback.** Production node104 remains frozen at D144 slot14 source `d49cb6d1bb24fa3d2496ca4564aaf1d4ea91fa5b` by operator directive. No live node observation or physical action was performed for this investigation.

At displayed 22:21, event `Переход в Mix`, reason `main_tail_hold_complete_recovery_mix`: displayed target 16.50 V / 2.40 A; actual 14.80 V / 0.20 A, CV, 24.0 °C. Subsequent graph/control card shows EFB 80Ah AUTO·MIX, programmed 16.50 V / 2.38 A, CV, Imin 1.85 A, ΔI +0.54 / +0.55 A (as rendered). The displayed 2.38 A versus 2.40 A target is not independently verified as an error; distinguish recipe ceiling, observed programmed setpoint and UI rounding.

At displayed 1:23, Telegram safety alerts:

1. `Защита V2: critical runtime telemetry is stale/incoherent: battery_voltage stale age=23.7s>20.0s. Автоматическое управление приостановлено до валидной телеметрии/защиты.` Displayed actual V=16.50 V / I=2.39 A / T=30.0 °C, CV.
2. `Защита V2: authoritative set_voltage readback V2 is missing/stale. Автоматическое управление приостановлено до валидной телеметрии/защиты.` Same displayed measurements.

**Source-level preliminary tracing:** `managed_runtime_safety.py` `_runtime_freshness_error` derives the first message via canonical `telemetry_freshness` metadata; the required-programming check constructs the second message when `_programmed_evidence(live, "set_voltage")` returns unavailable. The screenshot alone does not establish whether callbacks were lost on one ESP connection, were staggered during Native reconnection, or whether the reported second failure comes from a separate metadata/control-path problem. The actual output state, lease, persisted session outcome and link timeline remain **UNVERIFIED**; the UI text 'управление приостановлено' is not proof that Output was physically switched OFF.

## Next safe investigation (source-only)

- Trace the origin, timestamp, freshness metadata and cache invalidation of `battery_voltage` and `set_voltage`, especially ESP128 reconnect batching and existing 300-second Native outage policy. Do not loosen the 20-second freshness invariant or 900-second hardware lease as a speculative fix.
- Reproduce the paired sequence with offline fixtures: (a) aged battery callback, (b) absent/stale authoritative programming callback, (c) partial Native reconnect, (d) fully recovered callbacks. Verify existing fail-closed behavior and established outage grace; preserve one safety owner.
- Compare one-cycle UI event sequencing and source timestamp to the precise runtime logs **only after separate read-only investigation is explicitly in scope**. Never treat the operator screenshot as fresh Native/HA evidence. No deployment, restart, START/STOP, firmware, setpoint, lease or database writes without separate operator authorization.
