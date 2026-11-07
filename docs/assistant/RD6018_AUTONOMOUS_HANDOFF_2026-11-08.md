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
