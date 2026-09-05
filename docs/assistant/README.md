# Assistant Documentation Index

This directory is the durable project memory for charge-strategy/controller work.

Do **not** reconstruct behavior from chat history when these documents answer the question.

## Source-of-truth order

1. **`V2_DECISION_LOG.md`** — accepted/rejected V2 behavioral decisions. Highest strategy authority.
2. **`V2_OPEN_QUESTIONS.md`** — genuinely unresolved strategy/calibration questions only.
3. **`CHARGE_STRATEGY.md`** — compact production strategy/reference.
4. **`PB_RECOVERY_V2.md`** — implementation architecture and authority boundaries.
5. **`V1_BEHAVIORAL_AUDIT.md`** — factual V1 audit against `main@8d3e2af9...`.
6. **`HISTORY.md`** — historical record/rationale, not a competing current source.

Supporting proof/calibration/design documents:
- `V2_VALIDATION_PLAN.md` — Draft -> physically validated pre-merge gate plan;
- `V2_SAFETY_AUDIT_2026-08-30.md` — second whole-runtime safety review and closed implementation defects;
- `OPERATOR_HMI_SPEC.md` — normative Telegram operator-HMI information hierarchy, alarm/control feedback and renderer boundary;
- `OPERATOR_HMI_WIREFRAMES.md` — concrete storyboard for idle/start/run/recovery/Mix/SAFE_WAIT/Cooling/Storage/Manual/diagnostic/containment screens;
- `MIX_ACTIVE_TIME_AUTHORITY.md` — implemented durable session-bound Mix active-time authority; Cooling/proven-OFF freeze the budget, restart never reconstructs it from Ah;
- `MIX_ADAPTIVE_CURRENT_CONTAINMENT.md` — software current-ratchet/persistence mechanism implemented; production headroom and RD current/OCP actuator authority remain physical-calibration gated;
- `MIX_TIMEOUT_POLICY.md` — implemented authority rule: exhausted Mix maximum is `MIX_TIMEOUT -> STOP_AND_DIAGNOSE`, not successful SAFE_WAIT/Storage completion;
- `COMM_LOSS_WATCHDOG_15MIN.md` — 15 min TTL / 5 min positive-ACK renewal is implemented in the V2 branch; exact ESPHome compile/flash and loss fault-injection remain BENCH gates;
- `EXTERNAL_TEMP_SENSOR_INTEGRITY.md` — accepted and software-implemented external battery-temperature integrity mechanism: stale/missing fail-close plus calibration-gated N-consecutive fresh-anomaly shutdown without weakening thermal limits;
- `SG_POLICY_V2.md` — physical SG access, hydrometer/correction and prompt contract (D053);
- `BANK_FAULT_CALIBRATION.md` — labeled-case workflow for Q004/Q013;
- `DYNAMIC_LOOP_CALIBRATION.md` — actual-cadence/noise/settling characterization for Q005/Q014.

These supporting documents never override Decision Log strategy. Where a supporting note explicitly refines an older terse decision whose code has not yet been migrated, treat the note as accepted target behavior and the older implementation status as pending reconciliation.

## Current branch boundary

Work in `refactor/pb-recovery-controller-v2`; keep `main` unchanged until physical/on-device validation and explicit merge approval.

Production V2 deliberately distinguishes:
- chemistry / intent / program / stage;
- Manual authority from Pb chemistry authority;
- commanded / configured-readback / measured RD values;
- durable diagnostic evidence from transient diagnostic action authority;
- raw external evidence from an explicitly selected corrected/derived view.

## Closed contracts that must not be rediscovered from chat

- initial AUTO `<12V PREP / >=12V MAIN` boundary;
- Normal full-auto vs Diagnostic no-auto-HV;
- Ca/EFB and AGM session-wide recovery budgets;
- 72h Main fallback semantics;
- Mix maxima remain Ca20/EFB24/AGM10 and are **active-Mix authority ceilings**, not target durations;
- normal Mix completion is accepted Delta evidence -> sticky 2h finish hold -> SAFE_WAIT -> Storage;
- exhausting the Mix active-time ceiling without an already accepted finish hold is `MIX_TIMEOUT -> STOP_AND_DIAGNOSE -> Output OFF`, never successful completion;
- Mix active-time authority is durable and session-bound, advances only while Mix cannot be proved OFF, freezes in Cooling/proven-OFF periods, and is never reconstructed from Ah after restart;
- Auto Mix direct entry;
- AUTO Manual-OFF is terminal side-condition only;
- 24–48h heavy-recovery rest is diagnostic recommendation, never time lockout;
- Manual may carry optional physical `battery_id` for history only;
- persisted Manual restores `INTERRUPTED` and requires explicit fresh re-authorization;
- diagnostic in-flight actions never auto-resume after restart; derived authority is recomputed from evidence;
- SG access is explicit per physical battery; AGM never SG; EFB/Ca/Flooded chemistry alone never grants access;
- manufacturer SG correction is explicit and never inferred; a temperature-compensated hydrometer is never corrected twice;
- generic EFB AUTO/Recovery/Conditioning chemistry ceiling is 16.5 V; 17.5 V is Manual/Custom outer authority, not an EFB entitlement;
- generic Pb automatic HV current authorization is no broader than the implemented ~0.03C Mix maximum; Manual/Custom current authority is separate;
- Mix adaptive-current containment may only tighten current authority after confirmed `Imin`; the durable ratchet is implemented but production headroom/measurement-floor/OCP-write authority is disabled until physical calibration;
- managed communication-loss watchdog is implemented in this branch as 15 min TTL with 5 min renewals for every managed Output ON; the exact ESPHome package still requires physical deployment validation before merge;
- a future native RD6018 Timer Off watchdog must be renewed from the same accepted controller heartbeat as the edge lease and must not self-refresh independently, so two 15-minute layers cannot stack into a ~30-minute blind-authority window;
- watchdog refresh never resets or extends the separate Mix active-time authority clock;
- external battery temperature is safety authority: missing/unavailable/stale `temp_ext` remains immediate fail-close once freshness is lost; fresh-but-suspicious values use an N-consecutive-new-source-sample detector, while hard thermal limits or physically proven disconnect/error sentinels remain immediate;
- repeated HA polls of one cached temperature sample never count as N anomalies, and a flat but freshly reported valid temperature is not itself a fault;
- a temperature-sensor integrity shutdown is durably latched, forbids automatic restore, and never auto-resumes merely because the next sample looks normal;
- production anomaly `N`/step/slope/range values and any raw RD disconnect sentinel remain deliberately unconfigured until physical calibration;
- SAFE_WAIT is Output OFF even across Cooling; incomplete Cooling continuation metadata never defaults to Main;
- Vin is PSU-health telemetry only, including production legacy-start/restore composition paths;
- managed runtime authority rejects stale/incoherent dynamic battery/output telemetry: HA `last_reported` is the preferred heartbeat, `last_updated` is compatibility fallback, while static Vset/Iset/OVP/OCP timestamps are never mistaken for liveness clocks.

## Current implementation landmarks

For exact current SHAs use branch history/PR; durable behavioral meaning is in the Decision Log plus the implementation closures recorded by the safety audit. Recent implementation groups include:
- corrected RD telemetry/readback and safety envelope;
- continuous runtime freshness for Vbat/I/T and energized V_OUT, using HA `last_reported` where available;
- measured V_OUT/current runtime limits and raw OPP/unknown protection fail-close;
- Cooling/session-recovery timing normalization, including SAFE_WAIT OFF preservation and durable restore validation;
- hypothesis/SG/dynamic-loop evidence;
- unified Manual authority and quick-command migration;
- AUTO semantics + Auto Mix + AUTO Manual-OFF;
- diagnostic action journal/restart recovery (D051);
- optional Manual battery identity + interrupted-request review/re-authorization (D052);
- SG access/correction/prompt contract (D053);
- generic EFB >16.5 V expert chemistry extension removed (D054);
- external-temperature source-aware anomaly detector, verified-OFF containment, durable latch and restart/reauthorization gate (D055); production anomaly constants and raw disconnect-pattern classification remain physical-calibration gated;
- labeled Bank-Fault calibration harness for Q004/Q013;
- raw probe characterization harness for Q005/Q014;
- edge safety lease code and ESPHome package tightened to 15/5; physical deployment/fault-injection pending;
- Mix timeout reconciled to terminal `MIX_TIMEOUT`, never SAFE_WAIT success;
- durable Mix active-time authority wired into production controller composition and timer/status reporting;
- adaptive Mix current containment ratchet/persistence implemented as non-actuating calibration-gated infrastructure.

## Operator HMI design boundary

The HMI redesign is deliberately staged after the controller/safety audit. `OPERATOR_HMI_SPEC.md` and `OPERATOR_HMI_WIREFRAMES.md` define the intended operator experience before renderer code is changed.

Research basis recorded in the specification includes:
- ISA high-performance HMI hierarchy/task-centered display guidance;
- HSE command-feedback, alarm clarity and alarm-flood principles;
- Telegram Bot API 10.3 Rich Messages and semantic button styles;
- Telegram Mini App mobile/responsive constraints.

Key design boundaries:
- primary native Telegram remains the safety-capable operator station;
- optional Mini App is secondary analytics/forms, never the only Start/Stop/status path;
- L2 main panel shows state/output/key telemetry/progress/attention, not raw FSM debug fields;
- warning/alarm/event are different concepts;
- command submission and physical result are distinct (`STARTING`, `STOPPING`, `OFF unconfirmed`);
- Rich Messages may become the preferred renderer only after real client compatibility testing; classic HTML/InlineKeyboard remains fallback;
- safety-critical Rich Message controls use simple tested button rows rather than experimental table-cell interaction;
- renderers never own actuator sequencing or authority.

The storyboard is a **review gate, not implementation**. Review it as four operator paths in the order defined at the top of `OPERATOR_HMI_WIREFRAMES.md`. Pass A (normal critical path) and Pass B (abnormal/safety path) block renderer implementation until explicitly accepted.

Current code may receive narrowly scoped wording corrections when it contradicts an already accepted V2 strategy contract; that does not mean the storyboard has been implemented.

## Validation boundary

Unit CI proves software contracts only. Before merge, follow `V2_VALIDATION_PLAN.md` for:
- exact ESPHome compile/flash and 15/5 communication-loss fault injection;
- RD telemetry/readback bench smoke, including HA source-heartbeat behavior for unchanged values;
- runtime stale-telemetry fail-close and static-readback no-false-positive checks;
- external-temperature probe disconnect/reconnect and anomalous-source-sample characterization, including raw registers 34/35 and HA source timestamps; use those traces to activate calibrated Class-C `N`/range/step/slope policy and any proven raw disconnect sentinel;
- safe-enable/verified-OFF/edge-lease fault injection;
- `MIX_TIMEOUT` physical OFF/no-Storage proof and Mix active-time restart/Cooling/OFF trace validation;
- adaptive Mix current characterization before any production current/OCP actuator integration;
- interrupted diagnostic-probe restart test;
- interrupted Manual restart/reauthorization test;
- representative real-battery AUTO and Auto Mix traces;
- Q004/Q013 labeled Bank-Fault calibration;
- Q005/Q014 actual RD/HA cadence, ADC/noise, current-step and reconnection characterization.

Q011 and Q012 are no longer open gates: their production contracts are D054 and D053. Q004/Q005/Q013/Q014 remain empirically open; Q015 remains final physical compatibility/merge gate.

## Maintenance

Whenever behavior changes:
1. add/update a numbered decision when strategy authority changes;
2. remove resolved items from `V2_OPEN_QUESTIONS.md`;
3. update `CHARGE_STRATEGY.md` when operator-visible strategy changes;
4. add deterministic tests;
5. keep `V2_VALIDATION_PLAN.md` aligned with new physical proof obligations;
6. record implementation-only safety closures in a dated audit note when they do not redefine strategy;
7. keep PR description aligned with actual production branch;
8. when operator semantics change, keep `OPERATOR_HMI_SPEC.md` and storyboard synchronized before changing renderers.