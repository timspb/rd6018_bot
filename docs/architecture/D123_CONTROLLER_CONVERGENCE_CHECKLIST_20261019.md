# D123 Controller convergence — rolling checklist (2026-10-19)

Legend: [ ] pending; [x] verified on exact commit. NEVER tick a checkbox on intention alone.

## Baseline, separation, evidence
- [x] Pin baseline `58321a866dd68195bf8264d1d9ebe7c18a60748f`, current existing branch, and workspace-only scope; owner map records there were no production-host modifications/access: `D123_CONTROLLER_OWNER_MAP_20261019.md` §§Production route and Legitimate eradication
- [x] Inventory every current `ManagedChargeController` method and state field, current active production caller and target owner; AST cross-check found no unmapped method names: `D123_CONTROLLER_OWNER_MAP_20261019.md` §§ManagedChargeController methods and State field inventory
- [x] Identify the single charge FSM instance, persistence/session writer boundary, execution port, runtime safety and main-guard checkpoint owners and their tests: `D123_CONTROLLER_OWNER_MAP_20261019.md` §Production route and authority boundaries
- [x] Exact baseline offline discovery at `58321a866dd68195bf8264d1d9ebe7c18a60748f`: **2,325 PASS / 8 skipped**, using only a synthetic local test token; no secret or network service was used. Final source run: **2,338 PASS / 2 skipped**. Logs kept under `/tmp/d123-baseline-unittest.log` and `/tmp/d123-final-unittest.log` for this task.
- [x] Track source metric: baseline `charge_controller.py` 2,594 LOC / 85 method declarations / 84 unique names; after P1 2,529 LOC / 84 declarations / 83 unique names (-65 LOC, two implementation methods removed, one typed extension hook added): `D123_CONTROLLER_OWNER_MAP_20261019.md` §ManagedChargeController methods

## P1 evidence cut
- [x] Identify MAIN plateau-clock/assessment call graph and lifecycle: old methods at baseline lines 1000–1082; tick caller, START reset, cooling/stage resets and operator-pause clock shift mapped in `D123_CONTROLLER_OWNER_MAP_20261019.md`
- [x] Move plateau state and first-stage assessment to typed `runtime.charge.evidence` API; old controller methods and `_v2_main_plateau_since` removed, with no forwarding methods
- [x] Preserve exact 15-minute backdating and 40-minute Ca/EFB threshold; preserve AGM 120-minute threshold. The five-sample/12-minute evidence quirk is characterized and documented separately for later decision.
- [x] Wire the sole existing production tick to the evidence owner, reset/shift through the same owner; no second producer/writer/runtime or evidence import back into controller
- [x] Targeted tests cover minimum refresh, five samples before event and existing early plateau event/backdating, near-target path, reset, backward timestamps, 40/120-minute thresholds, restart-empty clock, stage exit/reentry, upward thermal and downward voltage trends: `tests/test_main_sample_evidence_clock.py`; restore and safety regression in focused suites
- [x] Focused tests and static architecture guards PASS (106 focused tests); full offline discovery PASS (2,338 PASS / 2 skipped), `compileall` and diff check recorded in sprint evidence
- [x] Source-only evidence saved in `D123_SPRINT01_EVIDENCE_20261019.md`; exact commit SHA is recorded by the resulting D123 commit

## P2 session / trace
- [ ] Canonical session ID, battery ID, stage history and audit/trace lifecycle ownership moved
- [x] Pure trace point, shadow/event metadata, first-stage trace metadata and CV/CC session signal context assembly moved to `runtime.charge.evidence.trace_context`; `ManagedChargeController.tick` retains one call path for each output and one production caller
- [x] Direct CV/CC context, event metadata, stable trace shape, moved-body and owner-call-count tests added in `tests/test_d123_p2_trace_context.py`
- [x] P2b trace identity creation/restore moved to typed `runtime.charge.session.TraceIdentitySnapshot`; controller identity helpers and `_read_legacy_session_document` removed
- [x] Restored session enrichment uses `complete_session_document` plus the sole `runtime.charge.persistence` atomic writer; original keys and optional recovery/final SAFE_WAIT documents are retained or canonically removed by continuation state
- [x] Guarded checkpoint restore remains rejected before controller mutation/enrichment; regression proves session/revision/SHA bytes remain unchanged. Failed atomic replacement fails restore and retains original session; no actuator path is called
- [x] No controller session patch writer, `.v2.tmp` path or `os.replace`; architecture AST guard blocks reintroduction. Unused production cooling/finish/runtime-signal patch writers removed; extension schema remains on canonical save
- [ ] Remaining audit/session lifecycle and MAIN Guard restore admission ownership moved; P2 remains **partial**
- [x] Sprint 04 stage-history mutation, clearing and persisted-history reconstruction moved to `runtime.charge.session`; the stable `current_stage` property calls that canonical owner and existing serialized `stage_history`, `previous_stage`, and `last_transition_reason` keys remain unchanged
- [x] Stage-history parity/architecture tests cover a single recorded transition edge, no duplicate for an unchanged stage, transition metric reset, previous-stage update, and persisted field restoration: `tests/test_d123_p2c_stage_history.py`
- [x] Sprint 05 moved typed trace context construction, volatile fallback, and disagreement throttling/logging to `runtime.charge.evidence.trace_context`; capture admission/routing belongs to existing `recovery_trace_store`; required controller `recovery_trace_context` interface remains, old capture/log method bodies and counter fields are removed, and `record_shadow_trace` remains the sole DB writer
- [x] P2d regression covers stable point/shadow rows, deterministic restart identity, unavailable capture, storage failure isolation, repeat throttling, frozen diagnostic-only snapshot and AST single-writer/no-controller-body guards
- [x] Final Python 3.12 full discovery with synthetic `TG_TOKEN=123456789:d123-sprint05`: **2,353 PASS / 2 skipped** (2,355 total); `compileall`, focused 31-test set, import architecture guard and `git diff --check` pass; exact evidence: `D123_SPRINT05_EVIDENCE_20261019.md`
- [ ] MAIN Guard restore admission and remaining audit/session lifecycle ownership remain pending; P2 remains **partial**
- [ ] MAIN Guard restore admission ownership remains deferred; guarded restore stays fail-closed before mutation/enrichment
- [x] Sprint 03 focused tests, Python 3.12 offline full suite and compileall PASS; see `D123_SPRINT03_EVIDENCE_20261019.md`

P2b session identity/writer convergence, P2c stage history, and P2d trace capture
lifecycle cuts are complete on their committed sprints. P2 remains **partial**
because MAIN Guard restore admission and remaining audit/session lifecycle
ownership are still outstanding. See `D123_SPRINT05_EVIDENCE_20261019.md` for
the current cut and test counts.

## P3 modular stage orchestration
- [x] P3-1: MAIN -> DESULFATION effect is built as `MainDesulfationEffect` by the pure `runtime.charge.runtime.desulfation_entry.build_main_desulfation_effect`, then applied once through `apply_main_desulfation_effect`; `ManagedChargeController._enter_desulfation` is removed. `decide_main_transition` remains the sole decision caller; the existing downstream action/execution/verified-commit route is unchanged.
- [x] P3-1 parity gates cover typed action keys and values across Ca/Ca, EFB and AGM, attempt count, stage-history single edge, targets/blanking/plateau reset, protection limits, no setter route in the owner, and AST single caller/import direction: `tests/test_d123_p3_main_desulfation_effect.py`.
- [x] Existing bounded recovery, retry/Guard, SAFE_WAIT continuation, transaction, terminal, restart and rollback/fail-closed regression suites passed with the full offline suite; source result is not physical acceptance.
- [ ] Remaining P3 effect owners: MAIN + PREP and residual; MIX/final SAFE_WAIT; cooling/storage/done and Manual integration.
- [ ] MAIN + PREP and residual
- [x] Sprint 07 P3-2 DESULFATION completion -> recovery SAFE_WAIT uses a frozen typed effect in `runtime.charge.runtime.desulfation_completion`; two-hour decision gate, canonical strategy targets, typed continuation, one session mutation edge, exact OFF intent and downstream transaction path preserved. Identity validation rejects missing/stale session ID/generation before mutation; regression and persisted-session snapshot paths pass. See `D123_SPRINT07_EVIDENCE_20261019.md`.
- [ ] MIX + final SAFE_WAIT
- [ ] Cooling, storage/done, Manual integration
- [ ] Typed stage decisions and effects; execution owns all setters, verified commit, safety
- [ ] Source parity tests for each stage, fail-closed and replay paths

## P4 façade elimination
- [ ] `runtime.production_runtime` uses one canonical application charge owner
- [ ] No active `ManagedChargeController`, no obsolete controller entry, no `_apply_authoritative_decision`, no `_enter_*` owner duplicated
- [ ] Static architecture tests reject any transitional facade/monolithic regression
- [ ] Docs and eradication ledger corrected, with old closure evidence preserved

## P5 release
- [ ] Exact source SHA, full multi-version test matrix and clean git state
- [ ] No unintended changes to 900s lease, MAIN Guard, safety, recipes, OVP/OCP, ESP, HA priority or Manual
- [ ] Separate D090 release preparation / rollback/Native preflight in a later authorized deployment
- [ ] Supervised real acceptance (stage transitions, ratchet, recovery, restart) after source release gate
- [ ] Temporary development branches/worktrees pruned; final owner map and report preserved

## Live physical status, independent

Last read-only check: D122 `58321a866dd68195bf8264d1d9ebe7c18a60748f`, node104 PID106714, Output ON, 16.34 V / 0.81 A, safety lease armed, R16=normal. **This D123 task never issues hardware commands.** Existing 15.5 V supervised bench limit was exceeded by automatic desulfation; do not assume new physical authorization.
- [x] Sprint 07 final exact-source Python 3.12 offline discovery: **2,361 PASS / 2 skipped**; targeted P3-2/regression set **49 PASS**; `compileall` and `git diff --check` pass. Source-only evidence: `D123_SPRINT07_EVIDENCE_20261019.md`.
