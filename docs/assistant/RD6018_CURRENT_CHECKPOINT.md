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
