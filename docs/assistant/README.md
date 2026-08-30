# Assistant Documentation Index

This directory is the durable project memory for charge-strategy/controller work.

Do **not** reconstruct behavior from chat history when these documents answer the question.

## Source-of-truth order

1. **`V2_DECISION_LOG.md`** — accepted/rejected V2 behavioral decisions. This has highest strategy authority.
2. **`V2_OPEN_QUESTIONS.md`** — genuinely unresolved product/strategy/calibration questions only. If a question is absent here and has an accepted Decision Log entry, do not reopen it from memory.
3. **`CHARGE_STRATEGY.md`** — compact production strategy/reference for operators and implementation work.
4. **`PB_RECOVERY_V2.md`** — architecture/model details for the recovery controller.
5. **`V1_BEHAVIORAL_AUDIT.md`** — factual audit of what V1 on `main@8d3e2af9...` actually did across UI/FSM/actuator/persistence/watchdogs/diagnostics.
6. **`HISTORY.md`** — historical record and rationale; not a competing source of current truth.

## Current branch boundaries

Work in `refactor/pb-recovery-controller-v2`; keep `main` unchanged until physical/on-device validation and explicit merge approval.

Production V2 deliberately distinguishes:
- chemistry/intent/program/stage;
- Manual authority from Pb chemistry authority;
- commanded/configured/measured RD values;
- durable diagnostic evidence from transient diagnostic action authority.

Recent closed contracts that must not be rediscovered from chat:
- initial AUTO `<12V PREP / >=12V MAIN` boundary;
- Normal full-auto vs Diagnostic no-auto-HV;
- Ca/EFB and AGM session-wide recovery budgets;
- 72h Main fallback semantics;
- Mix 20/24/10 + sticky finish hold;
- Auto Mix direct entry;
- AUTO Manual-OFF is only terminal side-condition;
- 24–48h heavy-recovery rest is diagnostic recommendation, never time lockout;
- Manual may carry optional physical `battery_id` for history only;
- persisted Manual restores INTERRUPTED and requires explicit fresh re-authorization;
- diagnostic in-flight actions never auto-resume after process restart; durable authority is recomputed from evidence.

## Maintenance

Whenever behavior changes:
1. add/update a numbered decision;
2. remove any resolved item from `V2_OPEN_QUESTIONS.md`;
3. update `CHARGE_STRATEGY.md` when operator-visible strategy changes;
4. add deterministic tests;
5. keep PR description aligned with the actual production branch.
