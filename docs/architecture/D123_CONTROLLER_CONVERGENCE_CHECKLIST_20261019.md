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
- [ ] Session identity/restore and trace persistence ownership moved; retained in controller for this partial cut because `_write_trace_identity_to_session_file` is a separate direct file writer and migration needs coordinated use of the existing canonical atomic session writer
- [ ] Guard journal revision/hash + monotonic accrued ON-time and sticky Iset proof intact
- [ ] Atomic persistence, restart continuity-fail-closed and guarded restore negative tests PASS
- [ ] No second checkpoint writer or authority path

P2 is **partial** after Sprint 02. See `D123_SPRINT02_EVIDENCE_20261019.md` for
the exact cut, tested restart contracts, and remaining lifecycle work.

## P3 modular stage orchestration
- [ ] MAIN + PREP and residual
- [ ] DESULFATION + recovery SAFE_WAIT
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
