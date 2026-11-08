# RD6018 — Autonomous new-chat handoff, 2026-11-08

## Exact source and mandatory reading

Repository: E:\CODEX\rd6018_bot, user-owned origin https://github.com/timspb/rd6018_bot.git, feature branch feature/main-mix-countdown-display. Historical first-handoff baseline was `224b227`; latest source baseline verified before the current D061 checkout-attributes documentation commit is `d520022d1046e91a5d7ce959dc01284c13594e62`. **Always recheck actual HEAD, worktree, remote and running processes; a later documentation commit supersedes either SHA.** Historical origin/main inspection is not current release identity.

Read AGENTS.md, latest sections of docs/assistant/RD6018_CURRENT_CHECKPOINT.md, this handoff, docs/V3_PROJECT_RUNBOOK.md, docs/V3_MODULAR_ARCHITECTURE.md, docs/V3_UI_MODULAR_ARCHITECTURE.md, docs/RD6018_COMPOSITION_ROOT_MODEL.md, docs/OPERATOR_BUTTON_RULES.md. Safety/release authority referenced by AGENTS.md is mandatory before control work. Historical checkpoint and old chat text do not establish live node state.

## Autonomy boundaries

Autonomously allowed: HOME-PC source-only research, small non-actuating fixes, offline tests, documentation, commits, push to the VERIFIED owned origin on this feature branch. NOT allowed: writes/restart/deploy to node104, HA/ESP/firmware/config/state/lease/physical charging/output/setpoint actions, merge to main, remote cleanup, touching other projects, printing secrets, starting another Codex/orchestrator without explicit independent task. Production frozen D144 slot14 exact source d49cb6d1bb24fa3d2496ca4564aaf1d4ea91fa5b and backups/tags remain untouched. No live acceptance claim from source tests.

Canon: one owner of state/transition/persistence/safety, one Telegram panel and 60-second refresh/publisher, one action selector, one accepted SignalAnalyzer/MAIN/MIX clock, typed variables/recipe config; no parallel service, timer, authorization, proof gate, runtime, duplicate dispatcher, or growing monolith. Maintain existing callbacks and ownership wrappers. Do not touch the edge or charge algorithm to fix UI copy. If MCP reports "server is not initialized", check whether the prior operation completed and retry; never duplicate long-running test/agent runs.

User will create wake automation in NEW chat separately. Do not install wake tasks or create R7.2 routes here. Every wake is a new synchronous turn; do not claim background progress between wakes.

## Completed source-only state

- HMI presentation decomposed into focused runtime/ui/components: immutable read model, telemetry, safety, AUTO/Manual/HANDS_OFF/adopted MIX, Imin/Vmax/Delta/finish hold, details, text rendering, action keyboard, graph/back/more layout and compatibility state. Installed callbacks/publisher remain in operator_hmi.py; rules in application/operator_button_rules; labels in runtime/ui/labels/operator_actions.py.
- Existing TerminalPanelManager is used by both graph-open and range change (commit 0774f0d); no second publisher.
- A routed Telegram intent can continue only with status ACCEPTED; BLOCKED_BY_SAFETY and REQUIRES_CONFIRMATION no longer fall through into pause or read handlers (historical commit 2b88410). Latest source baseline before this handoff refresh: d520022; use actual Git HEAD as authority.
- Selected Windows offline UI/graph/ownership/recovery/terminal suite: 353 PASS plus 104 subtests PASS; compileall and git diff --check PASS. This is NOT a full-repository or physical run.
- User's EFB MIX screenshot: Imin 1.85 A, observed Delta +0.04 A, required about +0.55 A, Iset 2.40 A. The required rise lies near current limit; timing and practical CV reachability unproven. Do not change Iset, EFB max voltage or finish policy from this image. CV and CC target hints are read-only and preserve accepted analyzer evidence.
- External Cezar/WSL completion signals are not RD6018 test evidence; WSL report R72_WSL_AUTO_20261108_001 contained only "COMPLETED.", no acceptance details. R7.2 repair is outside this task.

## Prioritized autonomous work (small, useful steps, no cosmetic decomposition)

P1. Audit callback behavior in operator_hmi.py for pause/resume, refresh, operator_more, adopted MIX stop and graph; trace PanelLastMiddleware and runtime/ui/telegram/panel_lifecycle.py, TerminalPanelManager, wrappers. Assert one callback ACK, one L2 refresh, correct message IDs and no duplicate send/edit or graph race, correct blocked/confirmation behavior and expired callbacks. Keep the physical adopted-stop guard unchanged; NEVER invoke on real hardware. Fix a demonstrable defect with regression test; do not invent infrastructure.

P2. Validate single snapshot consistency: get_operator_snapshot -> get_operator_actions(snapshot=snapshot) -> hmi_state_from_snapshot, renderers and post-callback refresh. Cover AUTO running/paused, interrupted Manual, adopted MIX, HANDS_OFF OFF/ON, unowned Output ON CONTAINMENT, IDLE and stale telemetry. Test behavior, not function identity (runtime integration intentionally wraps render_operator_panel).

P3. Offline UI evidence edge cases: reset on newly accepted Imin, invalid/future clocks, correct MAIN intent/destination and hold, accepted durable CV/CC Delta after regulator flip, MIX finish hold and three-decimal target near Iset. No changes to physical decision or assumptions about voltage/cells.

P4. When these are stable, run broader source-only regressions (native 3 chemistries x 4 intents; guarded MAIN, D144 restore, safety, terminal UI), then Python 3.10+ and isolated Linux/full suite when useful. Prepare exact source release manifest offline ONLY. Deployment requires separate owner authorization and fresh direct ESP Native evidence, not an autonomous wake.

P5. If no real defects remain, report actual status and the next evidence needed; do not manufacture more abstraction or tests for their own sake.

## Repeatable tests (PowerShell, HOME-PC)

Set $p='E:\CODEX\rd6018_bot'; verify git -C $p status --short --branch, git log, and remote URL. Push-Location $p; set $env:PYTHONUTF8='1'. Select tests/test_v3_ui_*.py and tests/test_operator_*.py plus:
tests/test_hmi_navigation_components.py
tests/test_hmi_render_ownership.py
tests/test_hmi_state_branches.py
tests/test_hmi_auto_stage_progress.py
tests/test_hmi_live_measurements.py
tests/test_hmi_mix_threshold.py
tests/test_adopted_mix_progress.py
tests/test_manual_extrema_progress.py
tests/test_rd_ownership_recovery.py
tests/test_production_entrypoint.py
tests/test_link_session_recovery_policy.py
tests/test_d070_guarded_restore_hold.py
tests/test_d125_cold_start_recovery.py
tests/test_restart_restore_ha_composition.py
tests/test_native_recipe_restore_parity.py
tests/test_terminal_panel.py
Run .\.venv\Scripts\python.exe -m pytest -q <selected unique paths>; compileall -q operator_hmi.py runtime/ui; Pop-Location; git diff --check. Check exit codes; include newly added tests; this is a selected test cohort. Avoid running scripts that actuate node104/ESP/HA.

## Every stage

Before: check branch, remote, dirty state, and exact source owner. After: focused/extended offline tests, compile and diff check, append exact test counts/commit status/node104 untouched/remaining work to docs/assistant/RD6018_CURRENT_CHECKPOINT.md, update this handoff if plan changes, commit source and docs, push only to https://github.com/timspb/rd6018_bot.git on feature/main-mix-countdown-display, then verify clean/synced tree. No reset/stash/rebase/force push, don't hide partial failures. No automatic deploy and no physical action. User will schedule wake in the receiving chat.

## New-chat startup

Read this file and AGENTS/canon; verify actual HEAD, active processes and latest checkpoint. **Do not restart the historical P1-P4 from scratch**: consult the latest completed records below, then continue only an open concrete issue or a useful independent offline release/recovery validation. Preserve source vs production distinction and never claim asynchronous work while idle.

## 2026-11-08 — Current P1-P5 outcome and next source-only decision

After the first handoff, P2 single-snapshot CHARGING/paused/adopted-MIX action parity, P3 MAIN Imin/hold and MIX accepted Delta display, P4 D144/recovery parity, and P5 Native readback freshness have been investigated and repaired in focused existing owner modules. Recent source commits include `bf9e449` (MIX proof/orphan keyboard), `dec6e62` (invalid MAIN recipe hold), and `d520022` (single pure ESP Native callback-batch coherence rule); read checkpoint for all intermediate SHAs, regressions and invariants. Native incident recorded in `docs/assistant/RD6018_V2_TELEMETRY_INCIDENT_2026-11-08.md`: paired battery_voltage stale/Vset readback missing can be independently reproduced in one connected stream, but real node104 cause remains **UNPROVEN** without live timestamped link and callback logs. Never claim the screenshots prove Output OFF.

Isolated WSL Ubuntu 24.04 Python 3.12 environment: `/home/home-pc/.venvs/pcp-test/bin/python`, already installed with the needed dependencies; do not create/install another interpreter unnecessarily. On current `d520022` baseline, focused WSL source-only cohorts: transport/safety/MAIN guard/D144/recovery policy **102 PASS**; session recovery/Output transaction/Telegram HMI **88 PASS**. Full `pytest -q tests` was attempted and interrupted after >3 minutes stalled near 14%: **437 passed, 2 skipped, 1 failed, 5 errors, INCOMPLETE**. The six D061 failures were exact-file checksum rejects caused by Windows checkout `core.autocrlf=true` rewriting fixed LF blobs to CRLF; canonical Git blob hashes remained correct. One source-only solution: add `-text` attributes to `tools/acceptance_guard/source-manifest.json` and six pinned overlay modules, then restore exactly the original Git blobs (do not repin digests, relax checks or change acceptance source). This yielded **D061 50 PASS**. Only the .gitattributes rules should appear as source changes; the pinned files must remain identical to HEAD Git blobs. Validate this after checkout/commit and record any further full-suite limitations accurately.

Prioritized next source-only work: verify clean Git and byte-pinned D061 assets after checkout; finish limited P5 acceptance/test packaging, and investigate only real remaining defects. Do not add parallel launchers, safety timers or authorization gates. Production remains frozen at D144 slot14 `d49cb6d1bb24fa3d2496ca4564aaf1d4ea91fa5b` pending separate physical owner authorization, source identity and read-only Native evidence.

## 2026-11-08 — D123 full-suite slice and historical worktree caveat

Post-`0b88927` read-only WSL collection finds **3033 tests**. D118 focused suite **40 PASS**. A bounded ordered full-collection slice IDs 400–520 initially showed three historical test-contract failures; fixed only tests: `test_d123_p2_trace_context.py` scans Git-tracked source instead of a nested independent `.worktrees/dryrun_virtual` checkout; AGM step and desulfation tests now require no redundant OVP/OCP writes per existing `charge_controller._add_phase_limits/_add_desulf_limits` policy. Focused changed tests **17 PASS**, the whole exact slice **121 PASS**. Do not change runtime charge/safety code to satisfy obsolete assertions. D061 byte-identity issue was already fixed with `-text` rules (50 PASS). The historical whole-suite attempt remains INCOMPLETE, not all-green. Continue bounded independent suites and investigate genuinely hanging test names; never delete/modify the valid secondary Git worktree, fake physical acceptance or auto-deploy to node104. Current Git HEAD after this documentation/test commit must always be rechecked rather than assumed.

## 2026-11-08 — Follow-up D123 Sprint57 bounded tests

After `039e373`, bounded full-collection IDs 521–700 initially returned 179 PASS, 1 FAIL; the historical OCP expectation in `test_d123_sprint57_guard_native_evidence.py` was inconsistent with the existing pure MAIN pre-ON assessor, which validates Output OFF/protection/Iset but never grants Output ON. Split the test, preserving fail-closed protection/Iset cases and verifying OCP is not a duplicate gate while `request_verified_on()` stays denied. Rerun bounded slice **181 PASS**. No runtime change. See latest checkpoint. Continue with bounded remaining suites rather than one unbounded full run; recheck actual HEAD after each commit. Do not act on node104.

## 2026-11-08 — P5 full-suite shutdown fix

After prior `f4e15cc`, a 200-test Linux source slice (1101–1300) printed PASS but hung in Python shutdown on non-daemon `aiosqlite._connection_worker_thread`. Independently identified Manual interrupted-restart test and MIX failed-cell-fault test as creators of unmanaged process-global DB connection; both now mock only the unrelated registry/history lookup. Existing real assertions remain. `test_manual_context` and `test_mix_mode` **13 PASS / exit 0**; full source slice **200 PASS / exit 0 (35.73s)**. The former whole-tree callback ownership scan now uses `git ls-files` to exclude nested worktrees. Temporary thread probe deleted. Continue with bounded collected IDs 1301–3033, recording exit code and any failures; do not launch another full uncontrolled pytest yet. Recheck actual HEAD and clean tree, do not use this text as a source identity assertion. Production node104 is unchanged.

## 2026-11-08 — P5 tracked production inventories and recipe first SET

Bounded WSL collected test IDs 1701–1900 initially 199 PASS/1 FAIL: Output-enable inventory walked a separate nested `.worktrees/dryrun_virtual` and falsely counted nine actuator paths. `tests/test_output_enable_inventory.py` now enumerates Git-tracked production `.py` in THIS checkout without modifying its frozen call-site list. Rerun **200 PASS, exit 0**. IDs 1901–2100 initially timed out at 56 PASS because production-module namespace tests recursively scanned nested worktrees/virtualenvs; their retired-module checks also saw only `__pycache__` directories for `runtime/application` and `runtime/charge/shadow`. `tests/test_production_module_namespace.py` now checks tracked production files and tracked retired paths, preserving exact forbidden symbols and modules. Rerun **200 PASS, exit 0**. IDs 2101–2300 initially 198 PASS/2 FAIL: first recipe SET test expected old OVP/OCP programming; recipe-policy graph test scanned nested worktree. Changed test expectation to Vset/Iset with omitted OVP/OCP (None), and scanned tracked production Python only. Rerun **200 PASS, exit 0**. These are test-scope and fixture fixes only, no physical command code edits.

Owner correction: routine OVP/OCP setting was **removed** on normal START and MAIN/DESULFATION/stage transitions, not merely skipped on some repetitions. Existing pre-ON boundary clears old positive OVP/OCP to zero when no explicit recipe-owned protection is requested, verifying readback; explicit MIX OCP is transaction-specific. Never describe old OVP/OCP thresholds as retained ordinary stage protection. Hardware trip status, chemistry/absolute V/I bounds, temperature, Output readback and 900s lease remain separate safeguards. Source safety/charge production unchanged. Next continue bounded IDs 2301–3033; full suite remains unaccepted until coverage + exit status established. No node104 interaction.

## 2026-11-08 — Актуальный план автономной работы

**План P1–P5 с новыми приоритетами:** `docs/assistant/RD6018_AUTONOMOUS_PLAN_2026-11-08.md`. Его блок P5-A заменяет прежнее требование начинать с P1 и содержит точный статус тестового покрытия, незакрытые диапазоны, правила завершения и ограничения production. На исходном базисе `99dacdd` участок 2301–2500 исправлен: тест legacy-аудита исключает вложенный Git worktree, Telegram `/start` изолированно закрывает DB в `asyncTearDown`; фокусные 3 и 4 PASS, весь диапазон **200 PASS / exit 0**. Следующий участок 2501–2700. Не считать весь suite принятым до проверки оставшихся диапазонов и контролируемого полного прогона. Не запускать node104.

## 2026-11-08 — Partitioned suite coverage completed

After baseline `3c5b16c`, all remaining original collected IDs **2701–2900, 2901–3033, 1–200, 201–399** completed exit 0, with two skips in the first 200. Earlier groups 400–2700 are in checkpoint; 3033-ID inventory was covered partition by partition. This is not a single suite PASS. Corrections: offline ESP fixture, tracked-source audits, outdated PREP→MAIN OVP/OCP test, and consolidation of Telegram markup construction in the existing renderer. Next run monitored full pytest with actual exit code. Production node104 remains frozen, no physical work.

## 2026-11-08 — P5 full-suite order dependency and HMI instance isolation

First continuous WSL full suite: **3030 PASS, 3 skipped, 1 FAIL, 6 warnings, 427.83 s**. The sole manual-interrupted callback failure was introduced at collection-time by globally stacked HMI wrappers: `rd_ownership_recovery` prepended `rd_ownership_hands_off` using its captured manager on another app. Existing wrapper is now app-bound: it never augments markup for `app_arg is not app`. Same-app behavior and all safety decisions preserved. New regression for own/foreign apps; focused 17 PASS, full collection with only former failed test selected 1 PASS. Re-run whole suite for genuine acceptance, node104 remains frozen.

## 2026-11-08 — P5 continuous full-suite PASS at d13d2cf

Actual owned feature HEAD `d13d2cfcce4401728e37d5481167aa5516fc363f` at test start, own remote `https://github.com/timspb/rd6018_bot.git`. Monitored uninterrupted WSL Ubuntu 24.04 isolated Python 3.12 `PYTHONPATH=tools:.:tests PYTHONDONTWRITEBYTECODE=1 /home/home-pc/.venvs/pcp-test/bin/python -m pytest -q tests` completed **EXIT 0: 3032 passed, 3 skipped, 6 warnings in 431.06s (7m11s)**. Earlier uninterrupted run at `4a5f7f6` was 3030 passed, 3 skipped, 1 failed and showed cross-app HMI wrapper ownership leak, fixed in `d13d2cf`, now proved resolved end-to-end. Warnings: 5 `datetime.utcfromtimestamp` deprecations `database.py:238` and 1 empty legend warning `graphing.py:203`, nonblocking, follow-up source-only cleanup. This PASS is entirely offline: no physical IO, no claim of live Telegram or node104 acceptance. Production remains D144 slot14 `d49cb6d1bb24fa3d2496ca4564aaf1d4ea91fa5b`, unchanged. Next: update plan/checkpoint/runbook, commit/push documentation; inspect one focused responsibility of oversized `runtime/production_runtime.py` (3635 lines) and incrementally extract only if a clear cohesive owner boundary exists, with new regression and full/targeted test evidence. Do not reimplement owner, or expand physical/safety surface. Freeze source-manifest only for exact final HEAD, offline, without deployment.

## 2026-11-08 — Incremental monolith decomposition: pure stage duration presentation

After verified continuous full-suite 3032 PASS / 3 skipped / exit 0 at `d13d2cf`, documentation baseline was recorded in owned branch commit `9a7a436`. For the next source-only stage, inspected `runtime/production_runtime.py` (3635 lines) and selected only its cohesive **pure UI duration formatting** responsibility; no charge-stage or hardware control moved. Relocated `_format_eta_compact` and `_format_seconds_compact` unchanged in semantics into new focused `runtime/ui/components/stage_duration.py` as `format_eta_compact` / `format_seconds_compact`, removed the old monolith implementations, and imported functions under their existing private runtime names. Added `tests/test_stage_duration_presentation.py` with invalid/blank/zero/hours/minutes/string input equivalence assertions. Existing stage progress, timer authority, counters, callback and publication paths unchanged. Focused WSL tests: `test_stage_duration_presentation.py`, `test_hmi_auto_stage_progress.py`, `test_operator_hmi.py`, `test_operator_button_rules.py`, `test_operator_dashboard.py` **82 PASS in 26.20s**. This is source-only decomposition and **not** a new continuous full-suite PASS after the change; previous full-suite pass was before extraction. No node104 or physical actions. Next: diff/compile, commit/push scoped module/runtime/tests/docs; inspect further monolith responsibility only with demonstrated single-owner extraction and regression, not mechanical splitting.

## 2026-11-08 — P5 full regression after stage-duration extraction

On tested source HEAD c32a37d19a5815a3e03c6ab503b03fba580acb38, the uninterrupted WSL isolated pytest -q tests completed: **3034 passed, 3 skipped, 6 warnings, exit 0 in 378.68s**. The extraction to runtime/ui/components/stage_duration.py also passed 115 focused HMI/Telegram/architecture tests. Five warnings are database.py:238 utcfromtimestamp deprecations; one is graphing.py:203 empty legend. This source-only result does not prove physical node104, real Native V2 callback events or live Telegram acceptance. Production remains frozen at D144 slot14 d49cb6d1bb24fa3d2496ca4564aaf1d4ea91fa5b; no node access, restart, deployment, output or physical command. Do not decompose further for file size alone; remaining work requires a concrete defect or separate live approval.
