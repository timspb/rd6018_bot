# RD6018 AD-002: ARCHITECT OWNERSHIP DECISION — 2026-11-12
**ПРИОРИТЕТ №1: ПОЛНАЯ ДЕКОМПОЗИЦИЯ И МОДУЛЬНОСТЬ. CHATGPT = АРХИТЕКТОР И ПРИЁМЩИК; CODEX LUNA = РУКИ.**

## Принятые факты
P2 owner inventory at .recipe-studio-local/mod_p2_ownership_inventory_20261112.csv: 478 existing production Python files / 478 unique, final_owner blank and review=True for all. 132 charge-engine candidate, 79 UI, 58 application, 54 physical, 22 safety, 82 REVIEW_REQUIRED. 200 flagged for potential side effects, 194 flagged for review. Duplicate import references inside CSV (e.g. triple production_runtime.py:40 -> ai_engine.py) are repeated import occurrences, not distinct dependency edges; do not use these counts for unique dependency KPIs. AST baseline source: 2276 eager, 232 lazy, 3 TYPE_CHECKING, zero eager cycles.

## Architectural owner assignments: rules, not mass file moves
- Battery/Chemistry: definitions, limits, pure calculations and policies; no hardware, HA, filesystem, Telegram.
- ChargeEngine: stages MAIN/MIX, Imin, 72h safety fuse and deterministic charge decisions, no direct physical IO.
- Application: START/STOP/SET/diagnostics/recipe use-cases, dependent on explicit ports.
- Safety Authority: single decision/admission/required-OFF policy; physical independent safeguards in ESP and runtime guards retained until proven parity.
- Physical Execution: one authorized write path/transaction through physical owner; runtime/physical and runtime/output are infrastructure, not their own safety policy; execution_port currently does not prove exclusive ownership.
- Telemetry/Evidence: ESP Native and HA snapshots, freshness/provenance/readback; runtime/charge/evidence must NOT default to ChargeEngine merely because of path.
- Sessions & Persistence: runtime/charge/persistence.py and runtime/charge/session_atomic.py belong here, NOT ChargeEngine.
- Recovery & Ownership: application/session_recovery_service.py, startup/adoption/HANDS_OFF/PB_MANAGED and session migrations, separate from generic application.
- UI: Telegram/dashboard/studio view-models and input dispatch only; no direct safety admission or HA commands.
- Composition/Configuration: runtime/production_runtime.py is MIXED 3429-LOC incumbent; eventual composition root only after extracting business responsibilities, not a single-file move. Root hass_api.py is HA/physical facade; manual_mode.py and charge_controller.py are mixed and require function-level ownership.
- Integrations: events, notifications, adapters, no second charge state owner.

## Work plan / explicit priorities
P2-A: deduplicate CSV import occurrences at source+target+kind+line granularity, verify reported unique graph edges vs AST baseline; leave AST canonical counts unchanged. No runtime edits.
P2-B: evidence-based review of 82 REVIEW_REQUIRED and 200 side-effect candidates. For all mixed/large files identify functions with multiple responsibilities and actual call-site or uncertain markers, no owner assignment without architect review. Distinguish active-wiring vs test-only/unconfirmed. Output exact source locations and candidate split seam.
P3-0: prove runtime physical command path callback -> application -> safety admission -> one physical owner -> HA/ESP; verify R16=3, 900s lease, verified OFF; do not conflate independent hardware protections with duplicative software policies.
P3-1: AFTER architect approves DTOs/Protocols and baseline tests, implement small vertical physical-path refactor with unit, integration, recovery and safety parity; no new frameworks.
P4-P9: Sessions/recovery, charge strategies, UI/integrations, composition/root cleanup, full regression and safe node104 deployment as already defined in RD6018_MODULARIZATION_MASTER_PLAN_2026-11-12.md.

No automatic final_owner filling. This ADR outranks path-only guesses. No git reset/commit/push or node104 physical changes during audits; source dirty tree preserved. R7.2 Codex up to two for bounded implementation, ChatGPT only for architecture and final checks.
