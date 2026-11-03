# RD6018 — CURRENT CHECKPOINT (2026-11-03)

Read this file first when resuming RD6018 work, then AGENTS.md and docs/V3_PROJECT_RUNBOOK.md. Older September handoffs are historical and may describe retired architectures.

## Current objective

Finish converting the existing charging programs (MAIN, Recovery/DESULFATION, MIX, SAFE_WAIT, PREP/COOLING/DONE) into versioned, configurable native recipes. There must be **one production algorithm/owner** for each stage, not a second simplified charge engine. Preserve original programs and all existing charge modes and user-created SET/OFF recipes. Reuse native controller safety, thermal compensation, MAIN guard, physical output ownership, and single canonical session document.

The visual drag-and-drop-style recipe editor is explicitly **deferred**, not abandoned. Prototype: tools/recipe_visual_editor_prototype.html, commit 1baea20. No live device interaction.

## Repo and deployment facts

- HOME-PC working tree: E:\CODEX\rd6018_bot ; own remote: https://github.com/timspb/rd6018_bot.git ; main.
- Pre-checkpoint code HEAD 5811349. Local main 111 commits ahead of origin/main as of this inspection; **GitHub not synced**.
- node104 last verified read-only 2026-11-03 12:53 UTC: rd6018-bot.service active, PID 196930, NRestarts=0, Telegram polling observed; control mode hands_off. Treat as timestamped evidence, not current guaranteed state.
- node104 contains the earlier native AUTO tick routing and read-only 12-variant Telegram catalog. **The newer native parameter editor, versioned copies, pinned-selection persistence, MAIN/MIX overrides, and native-copy START binding are local-only, NOT deployed.** Do not touch charging hardware. Before any deployment compare exact files and state on node104.

## Completed implementation

- Native variants: runtime/charge/programs/native_recipe_catalog.py describes 12 chemistry × intent variants. Original dynamic stage owners remain in service.
- Runtime parity: native_recipe_policy.py and native_recipe_runtime.py delegate MAIN/MIX/Recovery/SAFE_WAIT stage decisions and actions to existing charge owners. Parity tests cover independent and sequential ticks plus session restore.
- Single production AUTO stage routing via application/charge_session_tick.py, installed earlier on node104.
- Existing Telegram /recipes lists native variants in read-only mode (earlier deployment).
- Canonical VariableSpec parameter browser: native_recipe_parameters.py; later UI code not yet installed.
- Validated parameter copies: native_recipe_draft.py and native_recipe_draft_library.py, append-only versioned copies. Telegram commands /native_copy, /native_set, /native_show in code. Original native variants remain unchanged.
- Pinned immutable selected copy: native_recipe_session.py, recorded as native_recipe_selection_v1 in the **same atomic charge_session.json writer** (runtime/charge/session_atomic.py); restore validates identity and snapshot before modifying state. START resets previous selection.
- Native pinned MAIN/MIX voltage and C-rate overrides flow through existing select_main_target/select_mix_target and controller bounding; unpinned runtime remains unchanged.
- Telegram selection and canonical START path: production_bot_ui.py -> production_bootstrap.py -> application/production_start_route.py -> application/start_transaction_runner.py -> application/start_transaction_service.py. START rejects mismatched chemistry/intent, nonexistent version, and unsupported settings before energizing.
- Critically: ONLY wired MAIN/MIX settings are executable from native copies. Unsupported parameters remain draft-only. MAIN current C-rate limited to 0.1C. Dynamic Recovery/SAFE_WAIT parameters and transition policy overrides **still need execution wiring and validation**.

## Validation — do not overclaim

- Most recent focused Linux regression of native-copy START and related production routes: 82 PASS, 18 subtests PASS (prior to whitespace-only test amendment; latest commit 5811349). Additional target/session parity suites PASS.
- An earlier FULL repo run in the ambient WSL environment: 2812 passed, 9 failed, 5 errors, 3 skipped, 1510 subtests passed. Failure classes included missing aiohttp in a subprocess and stale/foreign test/artifact/architecture baselines. This is **NOT** a full PASS; inspect and reproduce cleanly before broad claims.
- Git working tree clean after 5811349; current docs checkpoint will become next commit. Remote GitHub sync remains unresolved; never push to foreign upstream.

## Next actions in order

1. Complete non-invasive native recipe parameter wiring: Recovery/DESULFATION and SAFE_WAIT time/transition settings, preserving chemistry/intent exclusions, and exercise on fake controller. Extend executable-key admission only when each key actually affects the correct production owner.
2. Add recipe editing/listing/version selection UX clarity in Telegram without accidental START, and ensure all supported overrides survive canonical session restore.
3. Run focused and full reproducible suites in a controlled Linux venv with no concurrent stale full-suite jobs; diagnose failures rather than manufacture acceptance gates.
4. Stage/deploy to node104 ONLY after tests, exact production file baseline, and hands_off/service state checks. Do not issue physical START/OFF/setpoint calls while an external charging process is ongoing.
5. Sync own GitHub origin once credentials and repository branch comparison are valid. No external upstream push.

## Mandatory continuity discipline

After **every substantive RD6018 stage/commit** update this checkpoint with (a) commit HEAD and local/remote delta, (b) exact implementation and constraints, (c) test results and remaining failures, (d) timestamped node104 deployment/control state and what is NOT deployed, and (e) next executable task. Update docs/V3_PROJECT_RUNBOOK.md when changing project canon or architecture. Documentation is part of the same stage: avoid code-only handoffs and avoid describing unverified hardware behavior. At a new chat, open this checkpoint before making changes.

## Implementation update — 2026-11-03 DESULFATION parameters

The following additional **local-only** native-copy parameters now use the original DESULFATION owner: `charge.desulfation.base_voltage_v`, `charge.desulfation.current_c_rate`, and `charge.desulfation.duration_hours`. They flow through `charge_controller._desulf_target()` and `runtime.charge.runtime.recovery_scaffold.apply_desulfation_authority_tick()` into canonical `select_desulfation_target` / `decide_desulfation`. The pre-existing temperature compensation, current ceiling, recipe bounding, and safe-wait transition owner remain unchanged. Normal AUTO without an explicit pinned selection uses original defaults. Diagnostic intent cannot select these parameters.

Focused Linux evidence before commit: **28 PASS, 137 subtests PASS**, including production restoration/START selection and DESULFATION strategy tests. This is not a full-suite PASS or physical proof. No node104 deployment or actuator operations. Remaining priority: SAFE_WAIT relaxation margin/timeout settings and other still-draft-only parameters, plus a clean isolated full suite; update this checkpoint with each subsequent stage.

## Implementation update — 2026-11-03 SAFE_WAIT relaxation

The canonical Recovery and Final SAFE_WAIT strategy owners now accept optional
pinned copy settings charge.safe_wait.maximum_hours and
charge.safe_wait.target_margin_v through
native_target_parameters(host, "SAFE_WAIT"). The existing runtime dispatch
and continuation/verified enable path are preserved. Output OFF freshness
remains mandatory even when the timeout is reached. No pinned copy means the
unchanged canonical defaults. Diagnostic native copies do not admit these
settings for execution.

Focused Linux regression at pre-commit state: **50 tests PASS and 437 subtests
PASS**, covering recovery/final SAFE_WAIT decisions, stale continuation parity,
session restore, START selection, and controller baselines. No full-suite PASS
claimed. This implementation is local-only; node104 is untouched, and its
last verified hands_off state remains timestamped earlier in this checkpoint.

Next: complete the remaining still-unwired native recipe settings including
MAIN transition controls and MIX finish timing; ensure UI and timer display
reports effective pinned values, not only canonical defaults; perform full
clean-suite evaluation before any deployment. Continue updating this file
with each implementation stage.

## Implementation update — 2026-11-03 effective recovery timer display

The runtime timer presentation in runtime/charge/runtime/support.py now reports
the **effective pinned** DESULFATION and SAFE_WAIT durations (when present);
both target_finish_time and stage_max_hours use the active session snapshot
and keep established defaults for unpinned AUTO. The periodic recovery
notification in runtime/charge/runtime/recovery_scaffold.py uses the same
canonical effective duration. No change to stage decision owners, safety
guards, or actuator routing.

Focused Linux tests: **23 PASS and 290 subtests PASS** before commit,
including dynamic SAFE_WAIT/Desulfation settings, timer presentation,
continuation/restoration parity and existing START. No full-suite or physical
acceptance claimed; node104 not deployed.

Next: remaining MAIN/MIX transition/finish timing parameters and any other
declared native options still rejected as not executable. Preserve a single
owner per decision and ensure runtime/UI metadata reflects effective values.

## Implementation update — 2026-11-03 pinned MAIN transition policy

The canonical MAIN transition dispatch in runtime/charge/runtime/main_scaffold.py
now consumes pinned native-copy values for fallback_hours, chemistry-specific
tail_hold_hours, and chemistry-specific max_recovery_attempts. The same
decide_main_transition strategy remains the only transition owner, including
its fail/stop behavior; a session without a pinned copy retains original
defaults. Updated executable-key admission rejects unwired settings, while
still rejecting MAIN current settings above 0.1C.

Focused Linux result: **61 PASS and 377 subtests PASS** for MAIN policy, Guard,
START, native execution parity, persistence/restore and controller paths.
No full-suite PASS claimed. Changes remain local-only; node104 untouched.
Next task: MIX finish-hold time settings and effective runtime timer reporting,
then remaining native parameters and the clean full suite.
