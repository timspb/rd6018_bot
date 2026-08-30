# Assistant History

This file is historical context, not the current strategy authority. Current behavior lives in `V2_DECISION_LOG.md` and `CHARGE_STRATEGY.md`.

## V1 -> V2 audit

V2 work began by auditing the complete V1 behavioral system rather than only stage transitions. The audit captured Telegram/operator paths, Pb chemistry FSM, RD6018 actuator sequencing, Home Assistant readback, watchdogs, persistence/restore, Manual/unmanaged paths, logging and diagnostics. The factual V1 baseline is `V1_BEHAVIORAL_AUDIT.md` against `main@8d3e2af9c2f16721f3303579f12d4f39bcc98a13`.

## Major accepted migrations

- Corrected RD6018 telemetry semantics and configured-value readback.
- Vin reclassified as PSU-health telemetry rather than battery chemistry authority.
- Absolute controller/manual working ceiling fixed at 17.5V; chemistry recipes remain lower where required.
- AUTO start made atomic: below 12V PREP, at/above 12V MAIN before first Output ON.
- Ca/EFB recovery count made session-wide; AGM given separate conservative four-attempt policy.
- 72h Main restored as strategy fallback rather than generic emergency timeout.
- Mix fallback normalized to Ca20/EFB24/AGM10 with mode-aware Delta and sticky 2h finish hold.
- Cooling converted to a real pause with frozen clocks and explicit continuity invalidation.
- Manual converted from unmanaged/Custom-adjacent behavior into a first-class managed authority.
- Bank Fault split into hypothesis-specific diagnostics; SG and two-wire dynamic-loop evidence added.
- Auto Mix added as direct-entry automatic Mix program.
- AUTO Manual-OFF fixed as terminal asynchronous side-condition only.
- 24–48h heavy-recovery rest fixed as recommendation/diagnostic window, not lockout.

## 2026-08-30 — diagnostic restart matrix and Manual identity/reauthorization

Two remaining software-only design gaps were closed.

### Diagnostic restart persistence

V2 now separates durable evidence from transient action authority. `diagnostic_persistence.py` journals diagnostic actions and applies fail-closed restart semantics:
- probe in progress -> `ABORTED_RESTART`; never resume mid-current-step; defensive Output OFF;
- pending operator/fault verification -> expired on restart;
- expert-HV authorization -> revoked on restart;
- rest observation may survive until expiry because it has no actuator authority;
- derived HV authority is recomputed from evidence rather than persisted as a permission token.

This closes former Q010 and is recorded as D051.

### Manual physical identity and interrupted request UX

Manual can now optionally bind to a saved physical battery for history/diagnostic correlation only. Saved chemistry/capacity never changes operator V/I or grants authority. The battery-bound input middleware is deliberately registered ahead of the generic numeric `V I` parser and has a regression test locking that precedence.

Persisted active Manual still restores `INTERRUPTED`. Operator can review the exact saved V/I, derived OVP/OCP, stop rules and battery identity, then explicitly re-authorize or discard. Re-authorization runs a fresh full safety/readback/Output transaction and starts a new active-time clock; it never silently resumes the old energized state.

This closes former Q002 and is recorded as D052.

## Current remaining work class

The remaining open questions are primarily physical/calibration/manufacturer-policy work rather than missing core software authority:
- Q004/Q013 cell-fault scoring calibration against real traces;
- Q005/Q014 controlled probe and RD6018 dynamic-loop/relay-path calibration on real hardware;
- Q011 expert EFB high-voltage workflow;
- Q012 SG correction/prompt policy;
- Q015 final physical/main-merge validation matrix.
