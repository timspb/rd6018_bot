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

`V2_VALIDATION_PLAN.md` is the proof/gating checklist for turning PR #2 from Draft into a physically validated candidate. It does not override Decision Log strategy.

## Current branch boundary

Work in `refactor/pb-recovery-controller-v2`; keep `main` unchanged until physical/on-device validation and explicit merge approval.

Production V2 deliberately distinguishes:
- chemistry / intent / program / stage;
- Manual authority from Pb chemistry authority;
- commanded / configured-readback / measured RD values;
- durable diagnostic evidence from transient diagnostic action authority.

## Closed contracts that must not be rediscovered from chat

- initial AUTO `<12V PREP / >=12V MAIN` boundary;
- Normal full-auto vs Diagnostic no-auto-HV;
- Ca/EFB and AGM session-wide recovery budgets;
- 72h Main fallback semantics;
- Mix 20/24/10 + sticky finish hold;
- Auto Mix direct entry;
- AUTO Manual-OFF is terminal side-condition only;
- 24–48h heavy-recovery rest is diagnostic recommendation, never time lockout;
- Manual may carry optional physical `battery_id` for history only;
- persisted Manual restores `INTERRUPTED` and requires explicit fresh re-authorization;
- diagnostic in-flight actions never auto-resume after restart; derived authority is recomputed from evidence.

## Current implementation landmarks

For exact current SHAs use branch history/PR; durable behavioral meaning is in Decision Log D001–D052. Recent implementation groups include:
- corrected RD telemetry/readback and safety envelope;
- Cooling/session-recovery/Mix timing normalization;
- hypothesis/SG/dynamic-loop evidence;
- unified Manual authority and quick-command migration;
- AUTO semantics + Auto Mix + AUTO Manual-OFF;
- diagnostic action journal/restart recovery (D051);
- optional Manual battery identity + interrupted-request review/re-authorization (D052).

## Validation boundary

Unit CI proves software contracts only. Before merge, follow `V2_VALIDATION_PLAN.md` for:
- exact ESPHome compile/flash;
- RD telemetry/readback bench smoke;
- safe-enable/verified-OFF/edge-lease fault injection;
- interrupted diagnostic-probe restart test;
- interrupted Manual restart/reauthorization test;
- representative real-battery AUTO and Auto Mix traces;
- calibration/open-policy gates Q004/Q005/Q011/Q012/Q013/Q014.

## Maintenance

Whenever behavior changes:
1. add/update a numbered decision;
2. remove resolved items from `V2_OPEN_QUESTIONS.md`;
3. update `CHARGE_STRATEGY.md` when operator-visible strategy changes;
4. add deterministic tests;
5. keep `V2_VALIDATION_PLAN.md` aligned with new physical proof obligations;
6. keep PR description aligned with actual production branch.
