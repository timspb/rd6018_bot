# Pb Recovery Controller V2

This document describes the implementation architecture behind the accepted behavior in `V2_DECISION_LOG.md`. The Decision Log remains authoritative if wording here ever diverges.

## Design boundary

V2 is not a single charging FSM. It is a composition of independent authority layers:

```text
operator program / intent
        ↓
chemistry + evidence strategy
        ↓
diagnostic transition veto
        ↓
actuator transaction / readback
        ↓
RD6018 physical output
        ↓
watchdog / edge fail-close
```

Manual is a separate operator-program authority and does not execute Pb chemistry transitions.

## AUTO recovery model

Main normal-tail evidence and stuck-plateau evidence are deliberately separate.

Ca/EFB session recovery budget = 3. Progress after an attempt does not reset it. After all three attempts, the next confirmed plateau may enter final Mix.

AGM session recovery budget = 4. Budget exhaustion never forces Mix merely because another plateau exists; AGM waits for its normal low-current tail or conservative 72h decision.

Recovery stage remains a bounded 16.3V / ~0.02C / ~2h corrective attempt, followed by Output-OFF SAFE_WAIT before returning to Main.

## Mix

Mix uses standard chemistry targets:
- Ca/Ca 16.5V;
- EFB 16.5V;
- AGM 16.3V;
- current ~0.03C, max 12A.

Evidence is regulation-mode aware:
- CV -> current minimum then confirmed current rise;
- CC -> voltage maximum then confirmed voltage fall.

Three spaced confirmations after post-setpoint blanking establish the event. The following ~2h finishing hold is sticky unless hard safety stops the run. Fallback maxima are Ca20h/EFB24h/AGM10h.

`Auto Mix` is a direct-entry program that creates the session already in Mix; it does not pass through PREP/Main/Recovery.

## SAFE_WAIT and Storage

SAFE_WAIT is Output OFF relaxation. Reaching the voltage threshold early continues immediately; otherwise the wait is capped at ~2h and then continues anyway. Timeout alone is not a fault.

Normal completion returns to managed Storage/float around 13.8V / 1A with Output ON. Terminal operator stop and faults are separate OFF outcomes.

## Cooling

Cooling pauses active program time rather than starting a new chemistry process. It preserves stage identity, exact target, recovery budget, AGM step, extrema and already-confirmed sticky Mix event. It invalidates continuity-dependent unfinished plateau/delta confirmation and freezes active timers. Restore must preserve the pause accounting.

## Manual authority

Manual request owns working V/I and operator stop rules. OVP/OCP remain derived and non-overridable. Envelope is 17.5V / 12A maximum.

An optional saved physical `battery_id` may be attached solely for longitudinal history/diagnostics. It does not import chemistry recipe, C-rate current or authorization into Manual.

After process restart, prior active Manual becomes `INTERRUPTED`. Review shows the saved request. Re-authorization is explicit and creates a new actuator transaction and a new active-time clock; Output is never silently re-enabled from persistence.

## Diagnostic evidence vs diagnostic action

Durable evidence and transient action authority are different things.

Durable evidence may include:
- SG measurements;
- completed dynamic-loop probes;
- recovery-cycle measurements/history;
- external test evidence when implemented.

Derived authority such as `BLOCK_AUTOMATIC_HV` must be recomputed from available evidence. It is not a persisted permission token.

Diagnostic action restart policy:

```text
probe in progress             -> ABORTED_RESTART + Output OFF defense-in-depth
operator confirmation pending -> EXPIRED_RESTART
fault verification pending    -> EXPIRED_RESTART
expert-HV authorization       -> REVOKED_RESTART
rest observation              -> may survive until expiry (no actuator authority)
```

A crash never resumes a diagnostic current step or guesses a previous current setting.

## Fault hypotheses

The old generic bank-fault score is only one evidence source. V2 reasons separately about:
- cell fault;
- self-discharge;
- sulfation/poor acceptance;
- stratification;
- capacity loss;
- thermal abnormality;
- charger/path fault.

A new automatic HV transition may be denied only by strong independent cell-fault evidence. Diagnostic inference never generates the hard-safety stop itself.

## RD6018 measurement semantics

`V_BAT` in the black+green two-wire charging setup is not Kelvin sense at the battery posts. Controlled `ΔV_BAT/ΔI` therefore represents the whole dynamic charging loop and must never be called battery internal resistance. Connection identity must remain unchanged for meaningful longitudinal comparison.

Commanded setpoints, configured/readback setpoints and measured physical values are separately tracked. Vin diagnoses upstream supply health, not battery chemistry.

## Restart principle

The general restart rule is:

> Persist evidence and safe intent metadata; never persist enough actuator authority to silently recreate an energetic action.

AUTO session restore, Cooling pause restore and Manual `INTERRUPTED` restore each follow their explicit contracts. Diagnostic work follows the action matrix above. Expert/high-energy operator permissions must always require fresh authority after restart.
