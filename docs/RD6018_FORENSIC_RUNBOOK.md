# RD6018 Forensic / Runtime Handoff Runbook

Last updated: 2026-09-13

This file is the canonical handoff note for the current RD6018 bot investigation. It exists so a new ChatGPT/Codex session can resume without reconstructing months of context from chat history.

## 0. Current intent

The user no longer wants to continue the legacy-removal/refactor plan until the current runtime is understood. The current bot is reported to have major functional errors. The immediate objective is forensic diagnosis and a production decision:

- `KEEP_V2_AND_FIX`
- `ROLLBACK_TO_V1`
- `V1_PLUS_SAFETY_CHERRYPICKS`
- `INSUFFICIENT_EVIDENCE`

Do **not** continue RuntimeApp extraction, legacy removal, controller decomposition, or safety consolidation while this forensic investigation is open.

Do **not** interpret a green unit-test subset as proof that production composition is correct.

## 1. Repository / branches / important SHAs

Repository: `timspb/rd6018_bot`

Observed repository branch heads at handoff:

- `main` -> `ef2b4806a16723eaff67451667d0a2c73fca8fc4`
- `codex/pr00-runtime-characterization` -> `c204429ccbab1e16beebe18a6be30884f11a4e4a`
- `codex/autonomous-validation-candidate` -> `bc4012c60f1d5ea9a40b016c45420f38672debd1`
- `codex/autonomous-safety-repair` -> `2657317f731cf0887ad48444a0c1234b288d263c`

Important historical baselines established by forensic audit:

- `V1_BASELINE=6da57edd35a0f263c84ab40889dd5a4705142a2e`
- `V2_START=591be3b882308aae872d8162db5f87107fa107df`
- `CURRENT=c204429ccbab1e16beebe18a6be30884f11a4e4a`
- merge-base of current working line with `main`: `8b5a3c4637f697793809a0c8ada8e2ea2285c5eb`

Forensic audit found approximately:

- 720 commits from V1 baseline to current
- 294 changed files
- about `+78,424 / -2,880` lines

First major introduction commits reported by audit:

- first `ChargeControllerV2`: `591be3b8`
- first `bot.py` V2 shadow composition: `0ebb145f`
- first production controller: `174346fc`
- first V2 manual: `1e111385`
- first ownership boundary: `a8526270`
- first AUTONOMOUS coordinator: `f769912b`
- first V2 safety layer: `085eb08c`
- first semantic HMI: `077fbb60`

Never assume public/default `main` and the working forensic branch are the same history. Re-fetch exact branch heads before any implementation.

## 2. Production / physical environment facts

Production bot node: `101`.

Home Assistant / ESPHome server: `192.168.1.102`.

RD6018 ESPHome device:

- hostname: `rd6018-controller`
- IP: `192.168.1.28`
- MAC: `C8:2B:96:30:FD:A5`

Known verified historical ESPHome production firmware baseline before autonomous candidate work:

- firmware `#23`
- source commit `49eed46159b30b7586cade573cfedbea278f9227`
- ESPHome `2026.8.2`

Production bot was previously rebaselined successfully to:

- commit `8b5a3c4637f697793809a0c8ada8e2ea2285c5eb`
- service `rd6018-bot.service`
- working dir `/root/rd6018_bot`
- venv `/opt/rd6018-bot-venv`
- rollback snapshot `/root/rd6018_bot-backups/preflight-20260910T063732Z`

That production rebaseline previously passed 899 tests and DB integrity checks, with Output OFF. Do not infer that current branch `c204429...` has been deployed to node 101.

The user strongly prefers a single minimal rollback point; avoid proliferating backups.

## 3. Non-negotiable safety invariants

Carry these into every analysis and implementation prompt:

1. `unknown != OFF`.
2. Never infer physical Output OFF from 0 V / 0 A.
3. Only canonical fresh Output readback proves OFF.
4. Verified-OFF semantics must not be weakened.
5. Fail-closed behavior must not be weakened to make tests pass.
6. Startup authority semantics must remain explicit.
7. `HANDS_OFF != AUTONOMOUS`.
8. `PB_MANAGED`, `HANDS_OFF`, and `AUTONOMOUS` are distinct authority states.
9. Do not auto-restore Pb charging when ownership forbids it.
10. ESPHome edge lease / authority contract is a physical safety boundary; no casual changes.
11. Do not change EFB MIX 20 h / 24 h semantics during refactors. They belong to different legacy/V2 authority paths and are separately codified by tests.
12. Do not increase timeouts or bypass guards merely to make CI pass.
13. Production node 101 is not an experimental target.
14. Safety-changing PRs require explicit bench/physical validation.

## 4. Current runtime architecture

Current composition is still module-as-app, not a `RuntimeApp` class.

High-level startup:

```text
python bot.py
  -> import bot_legacy as _legacy
  -> install V2/runtime monkey-patch layers onto the same module object
  -> create startup authority reconciliation task
  -> start physical-test/runtime helpers
  -> invoke bot_legacy.main()
  -> DB/init
  -> HA read
  -> session restore
  -> Telegram polling
```

`bot.py` eventually aliases the module namespace via `sys.modules[__name__] = _legacy`, so `import bot` effectively returns the `bot_legacy` namespace.

PR00 characterization established that the module-as-app namespace is heavily mutated:

- 69 distinct `app.<attr>` writes
- 62 writes from inside `install*()` functions
- 7 writes outside installer functions

Important owners observed:

- `charge_controller`, `manual_session_manager`, `charge_monitor`: installed by `v2_bootstrap`
- `runtime_safety_guard`: layered by `runtime_safety`, `runtime_safety_strict`, `runtime_safety_v2`
- `edge_safety_lease`: `runtime_safety_strict`
- ownership managers: their respective `rd_*` modules
- `_build_dashboard_keyboard`: written by multiple modules (six observed in characterization)

This last-writer-wins monkey-patch architecture is a major source of hidden behavior and must be treated as a forensic risk.

## 5. Controller inheritance / legacy scaffold

Current controller chain:

```text
DiagnosticProductionChargeControllerV2
  -> AutoStrategyProductionChargeControllerV2
  -> ProductionChargeControllerV2
  -> ChargeControllerV2
  -> ChargeController
```

Critical fact: V2 still executes the legacy scaffold via `super().tick()`.

V2 masks some legacy transition decisions/timers, but legacy code may still perform side effects before/after those decisions are masked. Do not equate “transition masked” with “legacy side effects harmless”.

Known shared/legacy state includes at least:

- `current_stage`
- `stage_start_time`
- `finish_timer_start`
- `_restored_target_v`
- `_restored_target_i`
- `_safe_wait_next_stage`
- `_safe_wait_target_v/i`
- `_safe_wait_start`
- `_safe_wait_v_samples`
- `_cooling_from_stage`
- `_cooling_target_v/i`
- `v_max_recorded`
- `i_min_recorded`
- `_delta_trigger_count`
- `_delta_trigger_mode`
- `_delta_reported`
- `antisulfate_count`
- `_agm_stage_idx`
- `_blanking_until`
- `_delta_monitor_after`
- `_first_stage_hold_since/current`
- `_stuck_current_since/value`

Historical legacy-removal planning concluded that dropping inheritance is a high/critical-risk operation and must not be attempted until persistence, stage mechanics, targets, timers, and state ownership are explicit. That project is currently frozen.

## 6. Output / actuator surface

PR00 inventory found 36 Output-related call sites (`turn_on`, `turn_off`, `safe_enable_output`) across 19 modules.

`bot_legacy.py` alone has 11 direct `hass.turn_on/turn_off` calls.

Direct calls are not automatically equivalent to an unguarded bypass: `HassClient` is wrapped by runtime safety/ownership layers. Therefore do not mechanically replace direct `hass.turn_on` with `safe_enable_output` while doing unrelated architecture work; that would change semantics.

Relevant actuator/safety modules:

- `safe_output.py`
- `runtime_safety.py`
- `runtime_safety_strict.py`
- `runtime_safety_v2.py`
- `rd_control_mode.py`
- `rd_startup_authority.py`
- `rd_managed_adoption.py`
- `rd_managed_mix.py`
- `manual_mode.py`
- `manual_runtime_v2.py`
- `v2_startup.py`
- `v2_mix_mode.py`
- `recipe_output.py`

Any actuator audit must prove the live object/install order, not merely that wrapper classes exist in source.

## 7. Restore chain / order-sensitive wrappers

Previous analysis derived the effective restore chain outer-to-inner as approximately:

```text
rd_hands_off_background
  -> rd_startup_authority
  -> rd_control_mode
  -> production_guardrails_v2
  -> done_storage_restore
  -> MixActiveAuthorityMixin
  -> ProductionChargeControllerV2
  -> ChargeControllerV2
  -> ChargeController
```

The order is behaviorally significant. Do not reorder it casually.

A future characterization test should prove not only call order but first-reject ownership for cases such as HANDS_OFF, startup authority not reconciled, managed ownership conflicts, DONE/Storage restore, and Mix authority conflicts.

## 8. AUTONOMOUS / authority work

The project introduced AUTONOMOUS as a separate concept from HANDS_OFF.

Required semantics:

- AUTONOMOUS is intended as a general-purpose PSU authority mode, not Pb-only.
- In AUTONOMOUS, Wi-Fi/HA/Telegram loss must not itself force shutdown.
- Pb chemistry/session/temp_ext are not required for autonomous operation.
- Local intrinsic hardware protections remain active.
- When bot sees autonomous authority, bot actuator/start/restore paths are blocked.
- Telemetry can remain readable.
- Edge autonomous state is persistent on ESPHome and treated tri-state during startup (`unknown/managed/autonomous`).
- While authority is unknown, bot actuator/charge-start/restore paths are fail-closed.

Candidate ESPHome package work introduced a persistent `rd6018_safety_autonomous_mode`, explicit enter/exit buttons, transition checks requiring fresh direct telemetry + confirmed Output OFF, and generation evidence.

Physical candidate validation previously established:

- device identity PASS
- boot baseline PASS with Output OFF
- autonomous enter PASS (OFF->ON, generation increment, Output stayed OFF)
- autonomous exit PASS (ON->OFF, generation increment, Output stayed OFF)

But some validation items remained blocked/not performed:

- bot control-boundary validation with separately running runtime
- physical Wi-Fi loss
- ESP reboot persistence

Do not overstate AUTONOMOUS as fully production validated.

## 9. PR00 legacy-removal characterization branch

An earlier legacy-removal project created PR00 characterization on branch `codex/pr00-runtime-characterization`.

PR00 originally added only:

- `tests/test_runtime_app_namespace_contract.py`
- `tests/test_legacy_enable_inventory.py`

Original characterization commit was `c2d51255e51c4bd082b0c7d0c21f86e334c29b1c`, based on `ef2b4806...`.

The branch later advanced to `c204429...` and now contains additional work/history. Do not assume branch name means it is still a two-test-only PR00 state.

Legacy-removal / RuntimeApp extraction is **frozen** until the forensic stability decision is complete.

## 10. Full forensic audit findings (V1 -> current)

A read-only forensic audit was performed for the range V1 baseline to `c204429...`.

Audit verdict was `KEEP_V2_AND_FIX`, but that verdict should be treated as a hypothesis, not unquestionable authority. The user is actively considering V1 rollback because real behavior is reported to have major errors.

### Confirmed defect D-STARTUP-1

Severity: HIGH

First bad commit reported:

`0880dcc0d03b7ac292f0ebbed15181cf5fcab5e9`

Last known good reported:

`d3464bedc18c88a8e5b4a067a5fc5353fc02701f`

Behavior:

1. `bot.py` starts `authority_task` concurrently with `_legacy_main()`.
2. `_legacy_main()` immediately performs `try_restore_session()`.
3. startup authority gate blocks restore while authority is unresolved.
4. delayed/unavailable edge read makes restore return `(False, None)`.
5. when authority later reconciles to managed, legacy restore is not retried.

Actual consequence: process/Telegram can continue running while an interrupted managed charge silently fails to resume.

This is fail-closed from a safety perspective, but functionally wrong and directly relevant to “bot alive but charging does not work”.

Important: restore failures are broadly caught/logged in legacy startup, so systemd process liveness is not proof of functional startup.

### Confirmed defect D-TEST-1

Severity: MEDIUM / compatibility-test contract

First bad commit:

`c34f6a91dd2e8c3a294766a0413b695566eff61c`

Last known good:

`646fab326dec94ce0872284b7fbcadf0bb2170c6`

`AutoStrategyProductionChargeControllerV2._run_legacy_scaffold_tick()` gained required parameter `manual_active`, while an existing direct test call did not pass it.

Production call site in `charge_controller_v2.py` reportedly does pass the parameter, so this alone is not evidence of production actuator failure. However, the full suite is not green and release must remain blocked until corrected and revalidated.

### Environment-only failure

`test_physical_test_control` relies on `asyncio.start_unix_server`, unavailable on Windows Python. This is a cross-platform test defect, not evidence of RD runtime regression on Linux.

### Full test snapshot from forensic audit

Reported:

- 1044 tests
- 2 errors
- 1 skipped

Focused passing suites included V2 entrypoint, namespace composition, autonomous install order, startup authority, edge autonomous, runtime safety V2, and SafeOutput.

Most tests are source/AST, isolated unit, FakeApp, or synthetic-adapter tests. Missing high-value composition evidence includes:

- real `bot.py` startup timing with delayed authority
- full Telegram update -> handler through real polling composition
- real HA transport composition
- production restart/restore integration
- physical RD/ESPHome validation

Therefore a green local subset must never be used as the sole reason to reject V1 rollback.

## 11. Hidden-error / observability concerns

Forensic audit counted roughly 233 broad exception / `return None` / unsupervised task patterns in production code.

Important classes of hidden failure:

- restore exception swallowed/logged while startup continues
- persistence/HA failures logged but process continues
- dashboard/Telegram handlers return fallback text rather than root error
- `asyncio.create_task()` without centralized task supervision

This creates a critical diagnostic distinction:

`process alive` != `bot functionally healthy` != `charge runtime healthy`.

## 12. Telegram / UI state

Current routing still uses the `bot_legacy` router plus V2/HMI installers.

Areas:

- `/start`, `/logs`, `/stats`, `/entities`, `/help`: mainly `bot_legacy.py`
- charge modes/manual: `bot_legacy.py`, `v2_bot_ui.py`, `manual_context_v2.py`
- dashboard/graphs: `operator_hmi.py`, `operator_dashboard.py`
- ownership/HANDS_OFF/AUTONOMOUS: corresponding installer modules

No confirmed callback collision was found in the forensic audit, but tests do not prove real Telegram polling/update dispatch with live HA behavior.

A prior real observation was that `/start` produced no response after autonomous-candidate flashing/runtime work. That symptom was not fully root-caused before the investigation shifted into architecture auditing. Treat it as unresolved evidence, not closed history.

## 13. Manual mode / latest current commit

Current branch head `c204429ccbab1e16beebe18a6be30884f11a4e4a` has message:

`fix: show manual mix finish evidence compactly`

It changes `operator_hmi.py` and `tests/test_operator_hmi.py`, including use of `MANUAL_MIX_FINISH_HOLD_SEC`, bounded displayed hold time, and display of Imin/Vmax plus delta evidence.

Manual mode forensic path:

```text
operator request
 -> parsing
 -> manual context
 -> session creation
 -> safe programming
 -> Output enable
 -> monitoring
 -> V2 finish evidence
 -> hold
 -> stop/persistence
```

No production manual-propagation regression was proven in the forensic audit beyond the broken direct test contract, but current manual behavior still requires end-to-end validation because the user reports broad functional errors.

## 14. V1 vs current forensic comparison summary

Forensic audit characterized current changes as intentional but high-risk in these areas:

- Bot startup: V1 direct monolithic startup -> current shim/installers/parallel authority. Confirmed restore race.
- `/start`: legacy dashboard -> semantic V2 HMI. No proven callback defect, but no real E2E proof.
- Auto charge: legacy FSM -> V2 authoritative transitions plus legacy scaffold. High risk, no proven general regression yet.
- Manual PSU: legacy custom mode -> V2 manual/session context. High risk.
- Mix: legacy transition -> V2 decision plus masked legacy scaffold. High risk.
- Output enable: direct guarded calls -> layered safety/readback/lease. Critical but no proven current bypass.
- Restart restore: immediate legacy restore -> authority-gated restore. Confirmed race/lost resume.
- Done/Storage: overloaded legacy state -> explicit persisted intent.
- Cooling: legacy cooling -> V2 continuation guards.
- HA loss: legacy watchdog behavior -> bounded fail-closed containment.
- Wi-Fi loss: managed watchdog -> ownership-aware behavior; physical proof incomplete.
- External Output ON: emergency/ownership decision -> bounded ownership grace/adoption.
- Telegram loss: polling/control loss -> intended separation from edge safety; E2E proof absent.

## 15. Rollback options already identified

### Option A — exact V1

Base:

`6da57edd35a0f263c84ab40889dd5a4705142a2e`

Pros: radically simpler runtime/composition.

Cons/risk:

- loses later readback/ownership/startup/autonomous safety layers
- DB/session semantics may be incompatible
- ESPHome contract differs
- would require deliberate state handling and physical validation

Do not perform blind rollback.

### Option B — V1 + selected safety cherry-picks

No clean minimal cherry-pick set has been established. Many safety changes depend on V2 state/composition. This option requires a fresh branch and independent dependency/physical validation.

### Option C — current minus/fix regression cluster

Preserve current V2/safety architecture, fix startup restore sequencing and other proven defects, then perform real composition + physical validation.

The earlier forensic report recommended this option, but user intent remains open because current real-world behavior is reported as badly broken.

## 16. Legacy-removal plan status

The earlier legacy-removal plan had a long PR sequence beginning with characterization and eventually moving toward RuntimeApp, session extraction, stage extraction, CycleState, controller composition, safety consolidation, and deletion of `bot_legacy.py` / `charge_logic.py`.

That plan is **ON HOLD**.

Do not continue PR01+ until current runtime stability and rollback direction are resolved.

The previous architectural insights remain useful:

- `legacy_recipe_adapter.py` is live, not dead legacy.
- `runtime_safety.py` still owns shared error/helper contracts for many consumers.
- `charge_logic.py` has many external constant-only importers but only a small number of true `ChargeController` behavioral consumers.
- EFB 20/24 difference must remain untouched during forensic work.
- restore wrapper order is sensitive.

## 17. What to do next in a new session

Default next task should be **deep forensic validation, not code changes**.

Recommended immediate sequence:

1. Re-fetch branch heads and exact current branch state.
2. Read this runbook first.
3. Read current `bot.py`, `bot_legacy.py`, `rd_startup_authority.py`, restore wrappers, `charge_controller_v2.py`, `auto_strategy_v2.py`, runtime safety layers, manual mode, HMI.
4. Reproduce/prove D-STARTUP-1 at code level and, if user requests, build a minimal production-composition test before patching.
5. Inspect the unresolved `/start` no-response symptom through real startup/router/HA dependency path.
6. Identify user-observed major errors explicitly; map each to code path and first bad commit.
7. Only after defects are enumerated decide current-fix vs V1 rollback.
8. If rollback is selected, prepare a migration plan for DB/session/ESPHome compatibility; never just `git reset` production.

## 18. Stop rules

Stop and ask/return evidence rather than continuing if:

- a proposed fix changes safety semantics beyond the identified defect
- restore precedence changes unexpectedly
- a new actuator bypass appears
- a test must be weakened to make code pass
- physical validation is required but unavailable
- repository branch assumptions are stale
- code under audit is not the same as production/runtime branch
- rollback would consume incompatible persistent state without a migration plan

## 19. Communication style / user expectations

The user wants concise but technically deep work. They strongly dislike:

- repeated planning/status messages without actual code/evidence work
- claims of autonomous progress when no tool work happened
- broad “looks safe because tests pass” conclusions
- documentation churn instead of fixing/diagnosing real behavior

When the user asks for a Codex/DeepSeek prompt, provide it immediately and make it operationally complete.

When working repo-side, use the GitHub connector and actually inspect/modify the repository rather than describing hypothetical steps.

For safety/runtime issues, distinguish clearly among:

- source-shape evidence
- unit/FakeApp evidence
- production-composition evidence
- physical RD/ESPHome evidence

## 20. New-chat handoff summary

If opening a new chat, tell the assistant:

- read `docs/RD6018_FORENSIC_RUNBOOK.md` on branch `codex/pr00-runtime-characterization` first
- current forensic line is `c204429...`; default `main` is still `ef2b4806...`
- V1 baseline is `6da57edd...`; V2 starts `591be3b8...`
- legacy-removal is frozen
- confirmed HIGH defect D-STARTUP-1 is lost managed restore due startup authority race
- confirmed MEDIUM D-TEST-1 is missing default/compat call for `manual_active`
- real E2E Telegram/HA/physical evidence is incomplete
- user is actively considering V1 rollback because real runtime behavior is reported badly broken
- do not conclude KEEP_V2 solely from green safety tests
- next work should be forensic and evidence-driven
