# RD6018 Autonomous Repair Incident Runbook

## Purpose

This is the coordination source for the autonomous-mode repair, separate from Codex/repo-agent reports. It tracks confirmed incident conclusions, invariants, completed repair boundaries and remaining validation gates.

# Incident

RD6018 moved away from the home control plane can lose Output because the managed communication lease was previously the only durable offline ownership model. Wi-Fi loss is not itself an RD hardware fault.

# Confirmed architecture

```text
Hardware safety != Application control != Control-plane availability
```

`HANDS_OFF` and `AUTONOMOUS` are distinct:

- `HANDS_OFF` = software ownership release / bot actuator block.
- `AUTONOMOUS` = explicit persistent ESP operation authority allowing generic PSU use without managed heartbeat availability.

Plain HANDS_OFF does not promise reboot/offline operation and never implies AUTONOMOUS.

# Safety invariants

1. `unknown != OFF`; V=0/I=0 is never Output-OFF proof.
2. AUTONOMOUS is never inferred from Wi-Fi loss, HA loss, HANDS_OFF or an unarmed lease.
3. Unknown/corrupt edge mode does not grant autonomous authority.
4. Managed D056 lease/Pb fail-closed semantics are not weakened.
5. AUTONOMOUS enter/exit requires fresh canonical Output OFF and positive edge mode/generation/readback ACK.
6. Ambiguous autonomous entry never silently restores PB_MANAGED; HANDS_OFF remains the conservative boundary.
7. Managed startup recovery may not actuate before explicit edge autonomous authority is resolved.
8. Stale HANDS_OFF -> PB callbacks cannot bypass explicit AUTONOMOUS exit.
9. HANDS_OFF live release leaves AUTONOMOUS OFF; D061 live adoption remains a separate HANDS_OFF transaction and rejects AUTONOMOUS.
10. Legacy Pb background workers are observational whenever Pb software lacks reconciled managed authority. They do not regain authority merely because raw telemetry is reachable.
11. Repo CI is not production/bench evidence.

# Generic autonomous safety evidence

Proven repo-side edge-local intrinsic authorities from D064 / merged PR #14:

- accepted internal RD/PSU temperature cutoff 55 C -> local Output OFF;
- fresh non-zero raw RD register-16 protection code -> local Output OFF.

Not yet proven as generic autonomous software ceilings:

- absolute voltage;
- absolute current;
- absolute power.

Do not reuse Pb values such as 16.6/17.5 V or 12 A as generic PSU limits. RD native V/I/power protection requires exact-firmware bench validation.

`temp_ext` is application telemetry in AUTONOMOUS. Missing/unavailable/stale `temp_ext` is not itself an autonomous fault. Any future autonomous external-probe emergency threshold requires separate physical validation; Pb 35/40/45 C policy must not be reused blindly.

# Repair status

## Phase 1 — Domain separation

DONE.

AUTONOMOUS means generic PSU operation, not autonomous Pb charging. Ownership and operation authority are separate.

## Phase 2 — Edge intrinsic safety

DONE REPO-SIDE / BENCH PENDING.

Merged PR #14 provides the proven intrinsic local guards above.

## Phase 3 — Explicit persistent AUTONOMOUS authority

DONE REPO-SIDE / BENCH PENDING.

Merged PR #15 (`98e0d4501cf48f8a539726d97f504f11fbfe0efc`) provides:

- persistent ESP autonomous bit;
- autonomous reboot independent of managed lease heartbeat;
- managed+autonomous conflict fail-closed;
- OFF-only edge enter/exit commands;
- positive Python ACK with mode + generation + fresh unarmed edge readback;
- global Bot/AUTONOMOUS coordinator;
- two-step Telegram confirmation for autonomous entry;
- final HMI switch composed after Output-truth normalization;
- bot actuator/start/restore block while autonomous;
- startup managed recovery gated on explicit edge authority;
- stale generic PB-return path blocked while AUTONOMOUS is active;
- HANDS_OFF release does not set AUTONOMOUS;
- D061 live HANDS_OFF adoption remains explicitly non-autonomous.

## Phase 4 — Legacy background authority isolation

IN PROGRESS on `fix/external-background-authority`.

Post-merge audit found that `bot_legacy.data_logger()` still executes Pb-era controller tick, restore probing, Manual-Off/operator-pause policy, host hard-stop claims and control notifications after the outer ownership layer has already moved to HANDS_OFF/AUTONOMOUS. Final actuator wrappers reject most writes, but the resulting exceptions can be reclassified by the legacy loop as HA/link-loss incidents and mutate stale Pb state or emit misleading control claims.

Required repair:

1. raw telemetry/database collection may continue;
2. controller tick and background restore are inert outside reconciled managed authority;
3. host Pb `_hard_stop_charge` is inert there because D064 owns intrinsic local protection;
4. stale Manual-Off/operator-pause authority is retired after explicit external ownership, but merely unresolved startup must not destroy their persisted managed state;
5. legacy Pb control notifications/events are suppressed while external/unresolved;
6. D065 task-local startup `recovery_scope` remains exempt so verified managed containment can execute;
7. reconciled PB_MANAGED and pre-commit live release retain existing safety behavior.

## Phase 5 — Repository validation

IN PROGRESS.

Required before the background-isolation merge:

1. exact-head Python 3.10/3.11/3.12 CI PASS;
2. production install-order assertion proving background isolation sees the final startup authority gate;
3. HANDS_OFF and explicit AUTONOMOUS background-inert regressions;
4. unresolved-startup sibling-task regression;
5. startup recovery-scope exemption regression;
6. managed/pre-commit safety regression;
7. durable D066 behavior decision.

## Phase 6 — Physical validation

NOT STARTED. Production unchanged; ESPHome has not been flashed by this repair work.

Before deployment:

1. flash the exact merged firmware;
2. prove AUTONOMOUS survives ESP reboot as designed;
3. with AUTONOMOUS Output ON, remove Wi-Fi/HA beyond the D056 TTL and prove communication loss alone does not OFF;
4. return to managed and prove D056 heartbeat loss still OFFs;
5. prove local 55 C and raw protection-code OFF on the actual node;
6. test power loss around autonomous persistence transitions;
7. characterize native voltage/current/power protection before declaring generic autonomous limits;
8. validate any optional external-probe emergency rule separately.

# Forbidden fixes

Do not use unlimited orphan timeout, global safety bypass, `RD_ALLOW_UNMANAGED_OUTPUT`, managed fail-close disable, V=0/I=0 as OFF proof, automatic arbitrary adoption, HANDS_OFF-as-AUTONOMOUS, or Pb chemistry ceilings as generic PSU limits.

# Evidence separation

Codex/repo-agent reports provide implementation findings/diffs/test output. This runbook owns incident classification, invariants, accepted repair boundary and validation gates. Neither replaces the other.
