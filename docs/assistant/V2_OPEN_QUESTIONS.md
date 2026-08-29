# V2 Open Questions

> This file contains only unresolved strategy/product questions.
>
> If an item is decided, remove it from here and record the decision in `V2_DECISION_LOG.md` in the same change.

## Q001 — Initial battery voltage >= 12 V: skip PREP atomically?

Known facts:

- below ~12 V the current must remain small;
- V1 can logically enter PREP while physically programming a Main target immediately when the starting battery voltage is already >=12 V;
- that one-tick logical/physical mismatch is implementation baggage, not an intentional chemistry mechanism.

Open decision:

Should V2 do this instead?

```text
initial Vbat < 12 V  -> PREP
initial Vbat >=12 V  -> MAIN directly, with explicit "PREP skipped" audit event
```

Need to decide exact hysteresis/boundary and restore behavior.

## Q002 — Manual mode schema and operator contract

Decision already made: Manual is a real supported mode, not a debug escape hatch.

Still to define:

- exact input format / UI;
- V target;
- I target;
- whether OVP/OCP may ever be entered manually or must always be derived;
- duration/stop conditions;
- optional explicit CV/CC expectation vs observation-only;
- whether battery identity/chemistry may be attached for logging without granting automatic chemistry transitions;
- how manual sessions are persisted/restored;
- how manual mode is represented in controller state (`MANUAL` vs separate authority dimension);
- whether a process restart may automatically resume Manual Output ON, or requires operator re-authorization.

Non-open invariant: global hardware safety, readback, thermal protection and watchdogs remain mandatory.

## Q003 — Manual OFF priority vs automatic controller decisions

Manual OFF remains an independent operator kill-condition system.

Need to define which automatic rules it suppresses while armed.

Candidate policy to review:

- hard safety: never suppress;
- explicit Manual OFF hit: immediately OFF;
- normal stage completion: likely still allowed;
- recovery/HV escalation: likely still allowed only if the operator's condition has not hit, but this needs a formal decision;
- time-based legacy chatter/reports: may remain suppressed for UX reasons.

The current legacy `manual_off_active` flag affects more behavior than a pure kill condition, so this must be normalized deliberately.

## Q004 — Bank-fault / cell-fault diagnostic authority

V1 has heuristic risk detection. V2 should build stronger, hypothesis-specific diagnostics.

Open question:

When does evidence become strong enough to affect actuator authority?

Possible levels:

1. advisory only;
2. warning + require explicit operator confirmation before next HV stage;
3. deterministic block of automatic HV when a defined fault criterion is met;
4. emergency OFF only for immediately unsafe electrical/thermal behavior.

Need separate fault hypotheses instead of one “bad battery” score, for example:

- shorted/weak cell suspected;
- excessive self-discharge;
- sulfation / poor charge acceptance;
- stratification suspected;
- dry/underfilled AGM suspected;
- overfill/rehydration issue;
- internal leakage / abnormal thermal behavior.

No single U/I sample should be treated as proof.

## Q005 — Controlled diagnostic probe design

The desired diagnostics may benefit from controlled probe/response measurements rather than only passive charge traces.

Need to decide whether V2 should implement bounded probes such as:

- small controlled current step (`ΔI`);
- measure immediate/short-window `ΔV` response;
- estimate dynamic resistance / polarization response;
- compare repeated probes across one physical battery's history.

Open parameters:

- which stages permit a probe;
- maximum amplitude/duration;
- thermal constraints;
- whether output must return to the exact prior setpoint transactionally;
- minimum telemetry freshness/sample rate required;
- how to distinguish wiring/contact resistance from battery response.

## Q006 — Enforced rest after aggressive recovery?

Operational idea: after a heavy recovery/Mix session, 1–2 days of rest may be useful for evaluation and battery settling.

Open decision:

- recommendation only;
- dashboard warning;
- longitudinal diagnostic window;
- or a hard software lockout preventing another aggressive recovery for 24–48 h.

A mandatory lockout has operational consequences and should not be added implicitly.

## Q007 — Normal/Diagnostic vs legacy automatic Mix behavior

Current V2 domain model separates charge intent:

- Normal/Diagnostic do not automatically authorize HV;
- Recovery/Conditioning may authorize it from evidence.

Need to keep validating this against the desired real-world operator workflow because legacy automatic profiles historically moved Ca/EFB toward Mix as part of the normal chain.

Before merge to `main`, explicitly confirm the intended user-facing meaning of:

- “Normal”;
- “Recovery”;
- “Conditioning”.

Do not let naming alone silently change the historic program selected by the operator.

## Q008 — 72 h Main fallback under the new intent model

The V1 Ca/EFB 72 h Main -> Mix behavior is accepted as intentional legacy fallback, not a defect.

Open V2 question:

How should that fallback interact with intent?

Options include:

- preserve only for Recovery/Conditioning;
- preserve for legacy-compatible auto profiles regardless of new intent naming;
- for Normal, finish/diagnose rather than Mix;
- require explicit operator confirmation after timeout.

This is separate from stuck-current recovery attempts.

## Q009 — AGM recovery-attempt budget details

Accepted principle: AGM is intentionally more conservative than Ca/EFB.

Need to confirm the final V2 policy for:

- maximum number of intermediate recovery attempts;
- whether the count is session-wide exactly like Ca/EFB;
- what happens after AGM's attempt budget is exhausted;
- whether final Mix is always permitted after the final 15.0 V Main step or requires additional evidence;
- whether rehydrated AGM condition modifies only diagnostics/envelope or also transition policy.

Do not copy the Ca/EFB 3-attempt rule by default.

## Q010 — Exact persistence semantics for Manual and diagnostic sub-states

Cooling semantics are now defined, but V2 still needs a complete persistence matrix for newer state that V1 did not have:

- Manual session;
- diagnostic probe in progress;
- operator confirmation pending;
- bank-fault warning/block state;
- expert-HV authorization;
- post-heavy-charge rest recommendation/lockout if implemented.

For every state define:

```text
persist?
restore automatically?
restore output ON?
require fresh telemetry?
require operator confirmation?
expire after how long?
```

## Q011 — Expert EFB high-voltage workflow

The absolute V2 software envelope supports up to 17.5 V, while ordinary recovery recipes remain lower.

Need to define an explicit expert path before 17.2–17.5 V can become an operator-selectable workflow:

- prerequisites/evidence;
- confirmation UX;
- current limit;
- time limit;
- thermal limit;
- battery condition exclusions;
- additional watchdog/readback requirements;
- logging/audit label.

Until then, 17.5 V is an outer safety envelope, not a standard recipe target.

## Q012 — Battery diagnostics: cell-level input model

If the operator measures per-cell electrolyte density/voltage or other external battery data, define how it enters the system.

Questions:

- manual entry vs external sensor integration;
- per-cell schema and units;
- timestamp/freshness;
- temperature correction for density;
- how missing cells are represented;
- whether cell imbalance can only warn or can block HV;
- how measurements bind to a saved physical battery and recovery cycle.

## Q013 — What qualifies as “confirmed fault” for automatic HV block?

Related to Q004 but must end as a deterministic contract.

A future rule should probably require multi-signal evidence, for example combinations of:

- abnormal open-circuit voltage / relaxation;
- repeated rapid decay;
- cell-level imbalance;
- abnormal thermal response;
- controlled probe response;
- poor Ah acceptance;
- repeatability across more than one observation window.

Need explicit thresholds and false-positive strategy before granting actuator authority.

## Q014 — Migration/removal of legacy side-channel heuristics

The legacy informational monitor can announce “almost full” from generic V/I thresholds independently from the managed FSM.

V2 already suppresses that contradiction during managed charging, but final cleanup should decide whether to:

- keep it only for Manual/unmanaged sessions;
- rewrite it as a generic hardware reminder;
- or remove it after explicit Manual mode is complete.

## Q015 — Final main-merge compatibility plan

Before merging V2 to `main`, define a traceable compatibility checklist:

- V1 auto-profile start behavior;
- low-voltage PREP;
- Ca/EFB recovery cycles;
- AGM staged Main;
- SAFE_WAIT;
- Storage/Done output ON;
- Manual output;
- Manual OFF;
- restart/restore;
- link loss;
- high-voltage watchdog;
- Telegram dashboard/operator messages.

Any intentional incompatibility should be documented in `V2_DECISION_LOG.md`, not discovered after deployment.
