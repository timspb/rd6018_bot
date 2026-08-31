# Mix Timeout Policy

Status: **ACCEPTED STRATEGY REFINEMENT / NOT YET IMPLEMENTED**

This note refines the semantics of the existing Mix fallback maxima. It does not increase any duration.

## Core decision

The Mix maximum is an **automation-confidence boundary**, not a target duration and not a reason to keep extending automatic high-voltage treatment for an unusual battery.

For Ca/Ca the existing **20 h** Mix maximum remains unchanged.

If a Ca/Ca battery reaches 20 h of active Mix time without the normal accepted completion evidence, V2 must interpret that as:

```text
normal automatic Mix did not converge
        -> battery is an atypical / unresolved case
        -> automatic HV authority ends
        -> operator/manual investigation is required
```

The controller must **not** increase the 20 h value merely because the battery still appears to be changing or may still be undergoing recovery/desulfation. Continuing such an experiment belongs to explicit Manual/operator authority, with the ordinary immutable safety envelope.

## Timeout is not successful completion

A Mix timeout must not be presented as normal successful completion.

In particular, timeout must not silently reuse the ordinary successful path:

```text
Mix finish evidence
-> sticky finish hold
-> SAFE_WAIT
-> Done / Storage
```

Instead it needs a distinct terminal/diagnostic outcome such as:

```text
MIX_TIMEOUT
-> leave high-voltage Mix safely
-> verified Output OFF
-> retain/log the Mix evidence and reason
-> tell the operator that automatic Mix did not converge
-> recommend Manual/diagnostic handling if further work is desired
```

Exact operator wording/state naming may be refined with the HMI work, but the semantic distinction is mandatory: **time expiry is not proof that the battery completed Mix successfully.**

## Why the limit should not auto-expand

A battery that needs more than the normal automatic observation window is precisely the case where automation should become more conservative, not less.

The timer therefore serves two purposes:

1. bounds unattended high-voltage exposure;
2. detects that the battery no longer fits the standard automatic recovery model.

The timeout is not a diagnosis by itself. It does not prove sulfation, capacity loss, cell fault, stratification, or another specific defect. It is evidence that further high-voltage work requires explicit operator judgement rather than continued automatic authority.

## Relationship to adaptive current containment

`MIX_ADAPTIVE_CURRENT_CONTAINMENT.md` and this timeout policy solve different failure modes:

- adaptive current containment reduces available current/power during an ongoing Mix and protects against blind acceptance increase;
- the Mix timeout bounds how long AUTO is allowed to remain in the high-voltage experiment at all.

Neither mechanism replaces verified Output OFF, thermal protection, OVP/OCP, fresh telemetry, or the edge safety lease/watchdog.

## Other chemistries

Existing fallback maxima remain unchanged unless separately reviewed:

| Chemistry | Current automatic Mix maximum |
|---|---:|
| Ca/Ca | **20 h** |
| EFB | 24 h |
| AGM | 10 h |

This decision specifically confirms the Ca/Ca 20 h boundary and establishes the general semantic rule that a fallback maximum is an automation boundary, not automatic proof of successful Mix completion. Any chemistry-specific timeout behavior that intentionally differs must be an explicit later decision.
