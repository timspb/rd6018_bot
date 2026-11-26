# RD6018 AD-008 — second architect primary-owner decisions, 2026-11-13

Status: APPROVED ten narrowly scoped PRIMARY MODULE department assignments, source-only architecture. Not hardware, runtime execution, safety, command authorization, deployment or behavior acceptance.

AD-006 original 5 approvals preserved verbatim in separate AD006 ADR/sidecar. AD008 approves EXACTLY the ten distinct primary modules below from independently reviewed P1-AD007B 20-module source report. Preserve imported APIs and current production implementation; NO move/actuation code change from this decision.

| Exact path | Approved primary department | Public boundary and limits |
|---|---|---|
| runtime/telemetry/snapshot.py | Telemetry/Evidence | Frozen TelemetrySnapshot carrier only; no freshness or ESP authority decision |
| runtime/charge/strategy/desulfation_variables.py | ChargeEngine | Desulfation VariableSpec config/seconds; preserve config defaults, no new policy values |
| runtime/ui/components/stage_duration.py | UI | Pure ETA/duration string formatting; no time owner |
| runtime/ui/components/main_stage_progress.py | UI | MAIN countdown presentation only, stage/timer owner stays ChargeEngine |
| runtime/ui/components/mix_stage_progress.py | UI | MIX hold presentation only, no separate timer/Delta owner |
| runtime/ui/labels/operator_actions.py | UI | Static presentation labels/callback identifiers, not action admission |
| runtime/ui/screens/help.py | UI | ScreenSpec assembly; Telegram transport stays external |
| runtime/ui/screens/analysis.py | UI | AI analysis screen DTO only; no AI provider/network ownership |
| runtime/ui/screens/stats.py | UI | Stats screen composition, no data store/actuation |
| runtime/ui/components/journal_filter.py | UI | Pure journal presentation projection, not persisted journal owner |

Evidence: .recipe-studio-local/REPORT_MOD_P1_AD007B_OWNER_BATCH_20261113.md contains exact function lines and import consumers; architect inspected the actual definitions in current dirty checkout (HEAD 3c69255). No direct hardware I/O observed in the ten modules. Existing dependencies are preserved; specific source-level approval does not imply runtime execution proof.

No approval yet for other ten reviewed modules, including runtime/ui/components/hmi_state.py and runtime/ui/telegram/renderer.py (safe reserve for independent next decision), and the 6 split/2 unresolved cases. No mass approval via 297 high-confidence proposals. No new physical/safety owner or new control path.

Reconciliation implementation contract: ADD NEW tools/architecture/reconcile_owner_decisions_ad008.py, tests/test_architecture_owner_decisions_ad008.py, .recipe-studio-local/mod_p1_owner_decisions_ad008_20261113.csv, and report .recipe-studio-local/REPORT_MOD_P1_AD008_OWNER_RECONCILIATION_20261113.md. Read previous AD006 480-row sidecar, retain its columns and all rows/values, add separate AD008 approval fields keyed by exact path; 480 unique rows, AD006 5 + AD008 10 = 15 approved total, remaining 465 unapproved. Detect duplicate or disagreement and fail closed. Do NOT modify AD006 sidecar or historical 478 inventory. Preserve final_owner as blank for compatibility until explicit future cutover. No filesystem/physical/HA/ESP writes except report/tool/test.
