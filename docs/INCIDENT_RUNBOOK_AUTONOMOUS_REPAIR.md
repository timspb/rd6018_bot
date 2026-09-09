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
10. Repo CI is not production/bench evidence.

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

IMPLEMENTED ON PR #15 BRANCH / REVIEW IN PROGRESS.

Current branch provides:

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
- HANDS_OFF release restored so it does not set AUTONOMOUS;
- D061 live HANDS_OFF adoption restored and made explicitly non-autonomous.

## Phase 4 — Repository validation

IN PROGRESS.

Required before merge:

1. exact current-head Python 3.10/3.11/3.12 CI PASS;
2. exact current-head canonical ESPHome compile PASS;
3. HANDS_OFF/AUTONOMOUS separation regressions;
4. D061 HANDS_OFF live-adoption regression;
5. startup authority-gate regression;
6. autonomous edge positive-ACK tests;
7. global transition tests including ambiguous command containment;
8. production install-order test;
9. numbered durable decision for the behavior change.

## Phase 5 — Physical validation

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
