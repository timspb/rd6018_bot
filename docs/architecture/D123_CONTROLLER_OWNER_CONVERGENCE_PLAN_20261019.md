# D123 — Convergence of charge ownership, without another legacy migration loop

Baseline: `58321a866dd68195bf8264d1d9ebe7c18a60748f` (D122 production code), 2026-10-19. Work exclusively in WSL2 Ubuntu-24.04 self-hosted workspace. **Source-only until full acceptance; live node104 stays on D122 while charging. No ESP firmware, service, GitHub CI, secrets or physical setpoint changes.**

## Problem and actual root cause

ERADICATION-02–09 removed historical `ChargeController.tick`, its inheritance/compatibility stack, alternative actuator and UI routes. But it declared victory with live `charge_controller.py::ManagedChargeController` (2,594 LOC) still owning `tick`, `_apply_authoritative_decision`, `_enter_desulfation`, `_enter_mix`, trace/evidence clocks and mutable stage transitions. `runtime.production_runtime` constructs it and invokes `tick`. `docs/V3_MODULAR_ARCHITECTURE.md` already forbids this architecture, while the eradication ledger and tests narrowly verify removal of old imports and fallbacks. We must finish ownership convergence, not recreate V4 or a second controller.

## Target architecture

`runtime.production_runtime` is existing composition/lifecycle ONLY. Existing `application` owns exactly one session tick orchestration and execution routing. Existing `runtime.charge` owns immutable stage/evidence/pure decisions and typed effects. Existing `runtime.safety` independently gates all intents; `application/execution_port.py` is sole physical writer/verified commit. Existing canonical `runtime.charge.persistence` + `session_atomic` own durable state and restore; existing UI reads detached snapshots. There is ONE production charging FSM, ONE actor per physical operation, ONE session identity and main-guard journal. Stage recipes remain composable: Ca/Ca/EFB/AGM/Manual unchanged. Do not add import-forwarding compatibility facades or historical `v2_*` namespaces.

## Work packages, in dependency order

- **P0 Inventory + measurable gates:** Create complete, evidence-based owner/caller matrix for `ManagedChargeController` methods and state fields, the live `production_runtime.py` call graph, required safety and restart invariants. Pin source tests to non-increasing boundary surface. Distinguish legacy code eradicated from current transitional orchestration. Freeze behavior with characterization tests. New tests fail on reintroduction of moved authority rather than mere file names.
- **P1 MAIN evidence and clock owner:** Move all first-stage evidence/plateau clock calculation and state mechanics from the controller to `runtime.charge.evidence` via a typed interface. Preserve actual 15-min backdating and 40-min Ca/EFB rule **for behavioral parity**; record separately the discovered time-evidence weakness for later approved algorithm adjustment. Remove implementation from controller instead of retaining wrappers. Route existing production tick to new owner, no alternative path. Prove exact transition parity and direct Native provenance/no invented ON-time. Commit/tests.
- **P2 Lifecycle, session and observations:** Move remaining `_v2_runtime.observe`, sampling and trace metadata, stage-history state, session restore glue into existing evidence/session/persistence owners. Application uses a single typed result and fresh Native authority. Preserve Guard checkpoint SHA/revision, original session IDs, no dual persistence writer or dangling shadow owner.
- **P3 Stage execution convergence:** Remove `_apply_authoritative_decision`, `_enter_*`, internal stage dispatch and effects dictionaries from controller; stage modules return immutable decisions/effects; existing application use-case coordinates verified physical transactions (incl. OFF/ON, 900s lease, Iset/OCP ratchet) and state commit. MAIN, DESULFATION, recovery SAFE_WAIT, MIX, final SAFE_WAIT, residual stages and Manual each have one owner. Do not move safety decisions into recipes or stage modules.
- **P4 Remove the transitional facade:** Migrate `runtime.production_runtime` to the canonical application interface; delete `ManagedChargeController` production ownership and obsolete controller file where no remaining direct callers. Remove transitional tokens/obsolete docs; no adapter bridge. Detect any new orchestration logic creeping into composition root.
- **P5 Release proof, cleanup:** Full Python 3.10/3.11/3.12 tests through self-hosted runner, no extra source regressions, same stage/target/transition behavior, full restart/restore negative tests, stage-specific safety and explicit physical acceptance before any production deploy. CLEAN source tree, remove abandoned temporary branches/worktrees after promotion, update `docs/V3_MODULAR_ARCHITECTURE.md`, runbook, `V3_LEGACY_ERADICATION_LEDGER.md` only on verified facts.

## Do-not-change invariant

Current production is D122: ESP Native is physical truth, HA only auxiliary; lease 900 seconds; OFF/readback/rollback fail-safe; OVP/OCP and MAIN Guard monotonic 1800s decreases; no unproven auto-output-ON after restart. The supervised **15.5 V trial limit is distinct** from existing automatic recipe ceiling 16.6 V; no live voltage or recipe modifications in this sprint. AGM chemistry and recipe choices untouched. Current charging session never mutated by architectural source work.

## Acceptance per package

1. Exact owner/caller map covers all public controller methods and all mutating/authority methods; explicit deleted vs remaining list and source file/line locations.
2. Existing regression suite and newly added focused tests PASS on same code HEAD, static gate records what has moved and blocks reintroduction.
3. No redundant production path, compatibility façade, direct hardware writer, independent journal, or reinterpretation of evidence.
4. A package is DONE only after source change, tests, clean diff, saved evidence and commit; source-only results are never mislabeled deployed or physically accepted.
5. Final DONE only when the production entrypoint no longer instantiates or invokes transitional `ManagedChargeController` and charge control follows the architecture contract, after separate supervised physical acceptance.

See `D123_CONTROLLER_CONVERGENCE_CHECKLIST_20261019.md` for rolling evidence.
