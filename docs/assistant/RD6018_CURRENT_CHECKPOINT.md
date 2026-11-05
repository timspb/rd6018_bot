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

## Implementation update — 2026-11-03 MIX finish hold

The native-copy setting charge.mix.finish_hold_hours now reaches the existing
MIX strategy decision through runtime/charge/runtime/mix_scaffold.py, not a
new engine. It also controls the runtime's MIX sticky-hold deadline and
stage_max_hours display in runtime/charge/runtime/support.py. Only native
copies with supported intent (not diagnostic) admit this override. Unpinned
MIX keeps the canonical 2-hour default. Later edits to the library cannot
change an already pinned session. The original delta evidence and active MIX
limit remain unchanged.

Focused Linux regression before commit: **56 tests PASS and 305 subtests
PASS** after updating an obsolete test that formerly rejected this key. The
full repository suite is still NOT green/fully validated. node104 was NOT
updated, charging actuation was NOT attempted. Last verified node104 state in
earlier checkpoint is timestamped, not a fresh health claim.

Next: inventory remaining declared parameters and ensure every executable
setting actually reaches its decision owner, with effective timer/UI output.
Repair the reproducible full-suite environment and historical failures before
staging a deployment. Update this checkpoint in every subsequent code commit.

## Implementation update — 2026-11-03 editable catalog execution parity

The native recipe parameters catalog now exposes only settings that the
existing production native charge owners can actually consume. In particular,
AGM uses staged MAIN voltages and does not present the generic fallback
charge.main.default_voltage_v as editable; DIAGNOSTIC mode does not present
DESULFATION, MIX or SAFE_WAIT fields. The editable copy of
charge.main.current_c_rate is bounded at 0.10C without changing the global
owner's VariableSpec declaration. Draft validation rejects unsupported
settings before START; no second charging algorithm introduced.

A new execution-parity test enumerates every visible variable in all 12 native
recipe variants and verifies that its default is accepted for a pinned copy.
Focused Linux suite: **27 PASS, 216 subtests PASS** before commit. This is
not full-suite or physical acceptance. node104 remains unchanged; only
local-source files were updated.

Next: separate audit of remaining production-only knobs (AGM staged voltage
editing and other advanced transitions) versus current recipe capabilities;
do not claim all physical behavior is editable yet. Run a clean full test
suite with correct dependencies, then stage a controlled node104 deployment
only after exact baseline and live hands_off checks. Continue checkpoint edits
in every completed code stage.

## Implementation update — 2026-11-03 AGM timeout tail-CV threshold

The existing runtime MAIN timeout strategy now consumes the optional pinned
AGM-only parameter charge.main.agm_timeout_tail_current_a. This is **not** a
change to the unconditional timeout policy: at the MAIN timeout, AGM
continues to MIX only with verified CV and current at or below the selected
threshold; otherwise the existing STOP_AND_DIAGNOSE path remains in force.
Unpinned and non-AGM profiles retain original behavior. AGM stepped MAIN
voltage table remains canonical and non-editable via the current scalar
native recipe drafts; do not misrepresent it as editable.

Focused Linux suite: **59 PASS, 170 subtests PASS**, including AGM policy,
native catalog, START/restore, safety guard, and controller regression.
Changes local-only, node104 not updated, no physical commands sent. A clean
full-suite pass remains outstanding; do not claim deployment readiness.

Next: inspect full-suite failures in a reproducible isolated Python
environment, distinguish missing dependencies/stale tests from actual
regressions. Keep the checkpoint current in each completed stage.

## 2026-11-04 full-suite hygiene checkpoint

Full Linux suite on a clean, detached fa005f5 Git worktree completed with
2848 PASS, 1 FAIL, 3 SKIPPED, 1666 subtests PASS in 164.44s.
The sole failure was D123 trace-context source AST scanning: a tracked Python
file carried UTF-8 BOM and ast.parse raised U+FEFF. The earlier dirty working
copy run was unreliable (2836 PASS, 8 FAIL, 5 ERROR) because source formatting,
historical pinned archive bytes, and generated artifacts differed; do not cite
that as a production regression.

Five tracked test-only Python files were found with leading UTF-8 BOM; their
BOM bytes were removed without changing Python logic. Focused Linux D123
suite after repair: 8 PASS. The full suite has NOT yet been rerun against
the new hygiene commit, so clean full PASS is not claimed yet.

No node104 deployment, no physical commands, no charge setpoint changes.
The local branch remains ahead of own GitHub origin. Next: clean full suite on
exact hygiene HEAD, then compare live node104 baseline with planned deployed
files before any production changes. Update this checkpoint in each stage.

## 2026-11-04 — Full repository regression PASS at exact HEAD

After removing UTF-8 BOM from five tracked test-only Python files in commit
c637922, reran the **entire** pytest suite in a separate clean detached Git
worktree /tmp/rd6018-clean-c637922 with HEAD c637922 (not the dirty
Windows worktree). The result is **2849 passed, 3 skipped, 5 warnings,
1666 subtests passed, 0 failed, 0 errors**, duration 169.61 s.
Evidence log: /tmp/rd6018-full-clean-c637922.log on HOME-PC WSL.
The earlier 1-failure clean run at fa005f5 was solely an AST source scan
tripping on UTF-8 BOM; this is now resolved. Historical D061/D145 pinned
archive problems observed on the mixed Windows worktree did NOT occur in
the clean worktree. Do not change those historical pins.

Production boundary is unchanged: node104 has **not** received the local
native recipe migration commits, control mode last read-only observed
hands_off, and no hardware commands or setpoint writes were sent.
Source/test PASS is not physical acceptance or authorization to interrupt
an ongoing charge.

Follow-up priority: verify the exact code and runtime state on node104
read-only, compare production baseline with current local HEAD, confirm
existing charge/graphs/bot behavior, then prepare a minimal deployment
plan preserving the active charge session and the existing single owner.
Review the accumulated gap to own origin/main before push; no foreign
upstream push. Keep this checkpoint updated with each subsequent stage.

## 2026-11-04 node104 read-only baseline after full regression

Read-only node104 probe (remote clock 2026-11-03T14:16:24Z): service active,
MainPID=196930, NRestarts=0, persisted control mode hands_off version 1.
The installed runtime/ui/telegram/recipe_buttons.py SHA-256 was
2f57c300be58de75fe6f3c03d2f67a093250b510e7c1b75f8d1ef664b7a3ca01,
consistent with an older deployed recipe UI. Polling startup was observed
in service journal; a later TelegramNetworkError request timeout at 13:37:46
was recorded. This isolated log error is not evidence that polling was
permanently down; monitor before asserting Telegram health.
New native-copy execution, START binding, and editor files remain local only.

The source branch HEAD immediately before this entry is 3cd4ead, with 121
commits ahead of own origin/main; no push was attempted. Untracked local file
charge_session.json.mix-authority.json was observed with an inactive
test-like session (145 bytes), but has NOT been deleted while historical pytest
processes remain visible. Keep it out of commits and investigate ownership
before cleanup. Do not deploy or touch the live physical charge.

## 2026-11-04 — Full node104 source-delta and activation boundaries

Pinned-host-key read-only source SHA256 comparison to production (remote clock
2026-11-03 14:22 UTC) includes **59 runtime files**: 13 identical, 40
different, 6 absent, no unknown. The machine-readable per-file manifest is
docs/assistant/RD6018_NODE104_DEPLOY_DELTA_2026-11-04.json.
The corresponding plan is
docs/assistant/RD6018_NODE104_DEPLOY_PLAN_2026-11-04.md.
Service uses root-owned app and rd6018-writable state; rd6018.db,
user_recipes, quarantines and MIX authority state are present. No active
charge_session.json located in the checked paths. hands_off remains enabled.
Do not infer that no external charge is underway.

Only a complete coherent runtime source release may be considered, after
isolated candidate tests and exact live recheck. No node104 writes, service
restart or physical actuator calls occurred. Next: inspect existing installer
and build full source release manifest. Keep this checkpoint current.

## 2026-11-04 offline candidate and D123 source-archive test

Exact source candidate was produced locally by the existing
tools/node104_atomic_deploy.py stage command at HEAD 82659d5. Verified archive
and release manifest; no node104 access or service action during staging.
Full source-only archive suite: 2842 passed, 9 skipped, 1 failed, 1658
subtests passed. Sole failure was D123 git-archive untracked-fixture test
requiring a .git checkout, which does not exist in a deployment source.tar.
The test is now conditionally skipped in archives but still executes in Git
checkouts; 5 D123 tests passed in a local checkout. Next: commit, restage
exact HEAD, and re-run archive and clean-checkout tests. Do not deploy yet.

## 2026-11-04 — Offline staged release full regression PASS

Exact source-only candidate fa60c16 produced by existing
tools/node104_atomic_deploy.py, archive and full extracted SHA256 manifest
verified. Full candidate suite: **2842 PASS, 10 skipped, 5 warnings, 1658
subtests PASS, 0 FAIL/ERROR**, 138.71 s. See evidence log
/tmp/rd6018-candidate-fa60c16-full.log on HOME-PC WSL. The increased skipped
count reflects absent .git in the source-only archive; source checkout D123
tests were 5 PASS. This is offline software acceptance, not physical
acceptance or node104 deployment.

The current node104 baseline remains hands_off, service running, and source
runtime mismatch: 59 changed source files of which 40 differ, 6 absent,
13 identical. Candidate must be treated as one coherent release rather than
a 6-file patch. Do not stop/restart the service or overwrite state during
an ongoing externally controlled charge. Next stage: inspect exact
candidate deployment handoff and prepare a reversible activation procedure
for a safe maintenance window, preserving all operational data.

## 2026-11-04 — production D090/D145 owner reconciliation

Найден существующий production CLI `node104_d090_transaction_live.py`: `prepare`, `activate`, `recover`, `--python-release-profile`. D145 binding входит в того же D090 владельца, использует установленную блокировку и не создаёт отдельный service runner. `tools/node104_atomic_deploy.py` — лишь офлайн-упаковщик.

Свежая read-only проверка node104 (удалённое время 2026-11-03 14:45:41 UTC): `rd6018-bot.service` active, PID 196930, NRestarts=0; `rd_control_mode_v2.json` = `hands_off`. На узле существуют `/opt/services/rd6018-bot/d090/node104_d090_transaction.py`, `app/tools/node104_d124_release_profile.py` и журнал `/opt/services/rd6018-bot/D090_TRANSACTION.json`. Журнал имеет фазу **STARTED**, `source_sha=930239c670899e14ccb09154d99baf77df90da10`, поле `candidate_inventory` отсутствует. При этом `.deploy_sha=58321a866dd68195bf8264d1d9ebe7c18a60748f`. Этот исторический журнал не является корректным новым COMMITTED релизом; его нельзя переписывать или удалять для обхода проверок.

В исходном D090 `_layout()` явно отвергает существующий журнал до нового `prepare/activate`, поэтому запуск новой транзакции прямо сейчас невозможен даже при исправном архиве. Действующий D145 transition ожидает именно исторический `STARTED` без `candidate_inventory`, но требует отдельной сверки его точного профиля source/preimage/collector со свежим node104. Не менять D090 или D145 наугад, не добавлять новые доказательства и авторизации: требуется использовать существующий жизненный цикл и восстановить согласованность активного состояния.

**Развёртывания не было.** Проверенный offline-кандидат `fa60c16` не установлен; аппаратные команды, systemd stop/restart, state/ и журнал D090 не изменены. Следующая конкретная задача: проверить, какой D145 binding реально установлен на node104 и какие операции существующий owner поддерживает для перехода из `STARTED`; сопоставить точный установленный source с D090 marker/preimage; затем связать цельный релиз `fa60c16` с существующим Python-release profile без нового запускающего механизма.

## Дополнение 2026-11-04 — наличие D145 на самом node104

Повторный read-only `find` по `/opt/services/rd6018-bot` (maxdepth 5) **не обнаружил файлов D144/D145**. В установленном `/opt/services/rd6018-bot/d090/node104_d090_transaction.py` есть `--python-release-profile`, но `_layout` по-прежнему отклоняет существующий D090-журнал (`existing/incomplete D090 journal requires recovery`). Локальный `d145_owner_binding_v2.py` из HOME-PC нельзя считать установленным производственным компонентом. Следующее действие — сопоставить локальный D145 с текущим D090 owner и провести офлайн-тест их совместимости на точной копии состояния `STARTED`, затем подготовить единый релиз/обновление существующего владельца. Ничего на node104 не записано.

## 2026-11-04 — D145 entrypoint test and byte-parity diagnosis

В локальном checkout `tests/test_node104_d145_entrypoint.py` + D144 owner/transition: **25 PASS, 3 FAIL**. Все 3 отказа — один и тот же D146 profile SHA: в Windows рабочем дереве `docs/operations/evidence/D146_D138_NODE104_PROFILE.json` переведён в CRLF (`git ls-files --eol`: `i/lf w/crlf`), SHA рабочих байтов `cabf0a0d…`, ожидаемый по Git blob `a2610e4c…`. В релизном архиве `fa60c16` файл имеет строго правильные Git-байты и **8/8 D145 entrypoint PASS**. Не переписывать исходный профиль и закреплённый SHA для обхода Windows-перевода строк; использовать clean Git archive/candidate.

Существующий D145 entrypoint в исходниках строго привязан к **старому** D146 source SHA `d351c208…`, preimage digest `9651e979…` и candidate identity `45b6ae0e…`; он не является универсальным launcher для `fa60c16`. Установленный node104 D090 журнал остаётся `STARTED` с source `930239c6…`, `.deploy_sha=58321a86…`; D145 на сервере отсутствует. Следовательно, нельзя запускать старый entrypoint на новом релизе или менять его SHA без сверки exact live preimage и контрактов D090/D145.

Исполнительный путь: использовать действующие `D090Transaction` и `D144 OwnerTransition` в офлайн-моделировании фазы `STARTED`, сверить реальный current app/venv inventory и D146 software release profile, затем готовить **один** согласованный релиз и путь установки через прежнего владельца. Пока node104 только read-only, зарядка и сервис не затрагивались. Полный релизный pytest `fa60c16`: 2842 PASS, 10 skipped; новая диагностика D145 не отменяет этот результат.

## 2026-11-04 — D137/D144 realistic offline regression

Added regression cases to `tests/test_d137_observed_preimage.py` and `tests/test_d144_state_preserving_transition.py`. Fixture based on the observed node104 condition: historical D090 `phase=STARTED`, source `930239c6…`, no `candidate_inventory`, deployed marker different from the D090 source, and active `charge_session.json` absent. D144 successfully completes an isolated transaction preserving legacy journal and marker exactly, while keeping `state/` unchanged. D137 refuses to describe a missing session as retired, and does not clear a quarantined state. **18 PASS, 7 subtests PASS** with `PYTHONPATH=tools:venv/site-packages`. Initial import failure without tools on the path was environmental, not a test failure.

The current D137 observer insists on verified retired-session evidence and non-quarantined recovery; node104 currently lacks the session file. Do not fabricate a retired session or silently weaken this requirement during an external charge. The next step is a fresh read-only comparison of actual physical output/controller ownership and D090 preimage with the assumed observation. The existing D145 binding must only be used when its inputs match actual state. No production deployment/restart/actuation occurred.

## 2026-11-04 — node104 fresh read-only reconciliation after D137/D144 test

Remote node104 clock `2026-11-03T15:09:05Z`: `rd6018-bot.service` active, PID 196930, NRestarts=0 (start `2026-11-03 11:34:55Z`). Control mode `hands_off` unchanged. Active `state/charge_session.json` **absent**; recovery quarantine file present since 2026-11-01. `rd6018.db` was modified at 15:08:39Z (fresh writes consistent with telemetry/storage; not evidence of control over physical charge). `charging_history.log` last modified at 11:35:34Z. D090 journal last modified 2026-10-21, phase `STARTED`, source `930239c6…`, still no `candidate_inventory`, baseline contains app/env/marker/observer/state/unit/venv, backup name `d090-818df047a6e64a22905d6da900162a86`.

Combined conclusion: **legacy transaction is historical, not changing now**; D144 synthetic fixture supports preserving its exact old journal. D137 *cannot* produce its legacy retired-session preimage from the current absent session. Do not synthesize a session or clear quarantine. Existing verified offline candidate `fa60c16` remains undeployed. Actual external physical charge/Output state is not independently proven by these file/DB observations; do not restart service or actuate. Next work should use read-only HA/native owner observations to establish whether the physical charge is currently running and then use existing owner code to reconcile authentic state; don't add a second lifecycle mechanism.

## 2026-11-04 — physical Output ON confirmed; activation must remain deferred

Read-only Home Assistant REST observation performed on node104 at `2026-11-03T15:12:59Z` (node clock): `sensor.rd_6018_output_voltage=14.67 V`, `sensor.rd_6018_output_current=0.05 A`, `sensor.rd6018_rd_6018_output_power_v2≈0.82 W`, `sensor.rd6018_rd_6018_output_state_code_v2=1` (**Output ON**), battery voltage ≈14.66 V. Modbus safety age at 15:13:01Z ≈2.48 s, protection code 0. Lease remaining 0, persisted bot mode `hands_off`. The HA `switch.rd_6018_output` also reports on, but its last_changed/updated was earlier; priority evidence is the fresh output-state code and live V/I. This demonstrates active external hardware output despite absent `state/charge_session.json`. Absence of a bot-owned session is **not** proof that physical charging has stopped.

Added focused tests for D142's existing OFF-only proof on the observed hands_off Output ON (as well as independent HA/ESP source disagreement). No new guard was added: the unchanged D142/D090 release validator must reject ON while awaiting a genuine safe maintenance condition. Linux regression `tests/test_d142_readonly_prestop.py`, D137, D144: **27 PASS, 7 subtests PASS**. Do not stop or restart the bot, adopt output, take lease, or alter volt/current. Existing D090/D145 journal/preimage issue remains. Next: maintain the verified offline candidate and recheck physical state only read-only; do not activate while Output ON.

## 2026-11-04 — exact offline candidate 095e545 and physical status

Staged a **new exact-head source release** via existing `tools/node104_atomic_deploy.py stage` (no node104 writes): source SHA `095e545dcd092c84776f6196296f69848aff40e5`, offline candidate `/tmp/rd6018-release-candidate-20261104/release-095e545dcd092c84776f6196296f69848aff40e5-h78vpxwf`. Focused D137/D142/D144/D145 tests in extracted candidate **35 PASS, 7 subtests PASS**. Full extracted-candidate pytest **2848 PASS, 10 skipped, 5 warnings, 1658 subtests PASS, 0 failures/errors** in 141.58 s. Log `/tmp/rd6018-candidate-095e545-full.log`. Source-only archive intentionally skips VCS-only tests; this does not authorize physical activation.

Read-only HA REST (`2026-11-03 15:12–15:13 UTC`, remote clock) confirmed **Output ON** by fresh `sensor.rd6018_rd_6018_output_state_code_v2=1`, `sensor.rd_6018_output_voltage≈14.67 V`, `sensor.rd_6018_output_current≈0.05 A`, `sensor.rd6018_rd_6018_output_power_v2≈0.82 W`, battery voltage ≈14.66 V; Modbus age ≈2.48 s, protection code 0. `hands_off` and lease remaining 0 (lease sensor itself last updated 2026-11-02). The HA switch entity's last update was older, so fresh Output-state and measured electrical values are primary. **No active bot-owned `charge_session.json` does NOT mean OFF.** The existing OFF-only D142/D090 release condition must reject current output state; extra tests for ON and divergent HA/ESP claims were added without introducing a new guard.

**Deployment HOLD because physical Output is ON**; no service restart, physical START/OFF/setpoint change, takeover, or journal modification. On HOME-PC older pytest processes remain running despite completed historical logs; the untracked root `charge_session.json.mix-authority.json` is 145 bytes and may be re-created by their tests. Leave it out of Git/deploy and do not kill processes/erase their artifact without attributing ownership. New clean candidate is available for a later safe maintenance window; hardware status must be re-observed then. Next: reconcile historical D090 `STARTED` and current D137 retired-session assumption through existing owner only, when genuine physical state permits; do not fake retirement or install D145 while Output ON.

## 2026-11-04 — physical OFF confirmed; authentic D137 retired-v2 path

User explicitly stopped charging. Fresh read-only HA at remote `2026-11-03T15:25:46Z` confirmed `sensor.rd6018_rd_6018_output_state_code_v2=0`, `sensor.rd_6018_output_voltage=0 V`, `sensor.rd_6018_output_current=0 A`, `output_power=0 W`, battery voltage ≈13.86 V, Modbus age 5.28 s. node104 service remains Active PID 196930, NRestarts=0, bot `hands_off`. No physical commands issued by ChatGPT. As of that observation there is no operating physical charging output; **repeat live OFF checks before service stop/activation**.

Read-only state examination: `/opt/services/rd6018-bot/state/session_recovery_quarantine.json` has `owner=runtime.charge.recovery_quarantine_journal`, `schema_version=2`, `state=retired`, `quarantined=false`, and authentic retirement keys including `session_id`, `confirmed_off_evidence`, `retired_utc`. Canonical `charge_session.json` is absent. This is authentic post-retirement state, not a fabricated tombstone. Historical D090 remains `STARTED`, source `930239c6…`, marker `58321a86…`.

Changed only local `tools/d137_observed_preimage.py`: it now reads the existing **retired v2 quarantine without a charge_session.json** as an explicit `session_absent=true`, `session_sha256=null` preimage. The original retired-session-file path remains supported; symlink/unknown/missing retirement evidence is rejected. D137 does not claim *current* physical OFF; D142/D091 still independently verify that immediately before any stop. New D137→D138 fixture checks genuine no-session retirement and guarantees no state writes or false activation admission. Linux focus: **34 PASS, 10 subtests PASS**. No node104 deployment or service restart. Next: stage and fully test the exact new source revision, then reconcile the currently missing D145 installation/profile with D090 owner before any production switchover. Keep all operational state intact.

## 2026-11-04 — user stopped charge; new candidate and node104 source staging

User explicitly stopped charging. Independently checked HA twice: at remote `2026-11-03T15:25:46Z`, RD6018 `output_state_code_v2=0`, output 0 V / 0 A / 0 W, battery ≈13.86 V; at remote `2026-11-03T15:38:05Z` still `output_state_code_v2=0`, output 0 V / 0 A, battery ≈13.30 V, Modbus age ≈3.22 s. Node104 systemd service active MainPID=196930, NRestarts=0, control mode `hands_off` retained. There was no bot-owned charge_session.json; the existing quarantine file has authentic schema v2 `state=retired`, `quarantined=false`, retirement `session_id`, `confirmed_off_evidence`, `retired_utc`.

Implemented local source update `tools/d137_observed_preimage.py` to represent genuine no-session retirement v2 as `session_absent=true` and `session_sha256=null`, without manufacturing a session or asserting current physical OFF. Existing D142 independently checks live OFF. Added D137 and real D137→D138 integration tests, including invalid/unknown retirement and no state writes. Focused Linux **34 PASS, 10 subtests PASS**; commit `daa6bff2d8b2997884dbd7102c44a1d266950ba9` (code plus checkpoint).

Built exact Git source-only candidate `daa6bff` via existing `tools/node104_atomic_deploy.py stage`. Full extracted release suite: **2851 PASS, 10 skipped, 5 warnings, 1661 subtests PASS, 0 FAIL/ERROR**, log `/tmp/rd6018-candidate-daa6bff-full.log` on HOME-PC WSL, 137.98 seconds. Its `source.tar` SHA256 `8b61353b3fd9ca05901200825dfa7402fca295e20f3f5b569d381d11b4c197ed` (9,420,800 bytes); `RELEASE_MANIFEST.json` SHA256 `1eb08b777cf5f40ee1588bae121213b7e4327a99353b4b9e08f7912c7ed8b898` (256,087 bytes).

Transferred ONLY these two files to node104 `/tmp/rd6018_source_daa6bff2d8b2997884dbd7102c44a1d266950ba9.tar` and `/tmp/rd6018_manifest_daa6bff2d8b2997884dbd7102c44a1d266950ba9.json`. **Remote SHA256s match local exactly**; bot still active PID 196930 / zero restarts afterward. The subsequent attempted remote extraction into another `/tmp` path was rejected by the tool; DO NOT claim successful extraction. No installation, no service stop/restart, no D090 state/journal modification, and no RD6018 actuation performed.

Remaining release issue: installed production D090 journal still `STARTED` source `930239c6…` with no `candidate_inventory`, deploy marker `58321a86…`; D145 entrypoint in source still pins historical `d351c208…` and is **not installed** on node104. Reconcile exact D090/D145 owner profile and live preimage rather than forge retirement, change historical pins blindly, install parallel bot, or bypass physical OFF evidence. Repeat fresh OFF observations before any operational switchover. Current source archive is staged only, not an activation-ready deployed release.

## 2026-11-04 — D145 prepare PASS; D148 POST_START root cause

node104 D138 completed on the actual installed preimage and a complete isolated Python 3.11 stage: `source_sha=daa6bff2d8b2997884dbd7102c44a1d266950ba9`, 1340 verified source files, Python 3.11.2 venv with `pip check` PASS (9351 regular files), observed D137 preimage SHA256 `9a3c035495a5f72d76ed7932d1fe2aa2c0e96a2dd97816f386518c9dbca0bd22`, D138 candidate identity `2b7acc9790fd1ed42b88ca4e8bbc01899f495e88f508e55712df0659b098a83c`, D138 manifest SHA256 `88f855475399a599f7e9f22b2c0bfebc2327c25403546cd14015cb17e766b75d`. Root-owned D147 observer was installed using the existing exact pin (`1127e9e3...`) and historical D148 observer (`a738f08e...`) installed from its original legacy stage; both read-only, unchanged service PID 196930. Exact D146 target profile was generated with actual current env/unit hashes and validated (`python_control_change`, 411 paths, no firmware change); SHA256 `a07457a755ceddb44e367ab0273fe53b9b9c94e24a03df39c0b5d87371f34c82`. Frozen existing D145 entrypoint copy for this exact target was staged in `/tmp`, SHA256 `66991fa62fcb1d60f6ecd44253904d7d96c0e976effdb60e46b6ef2ccae4c929`. D145 `prepare` returned **PREPARE_ONLY_PASS**, fresh independent OFF true, capacity true, matching candidate and preimage. No service stop or activation.

Before execute, independently tested D148 `POST_START` and found **failure**: `ProofError: quarantine journal is active or uncertain`. This was traced to the source D091 collector's logical bug: it validated `_journal_state(journal_path)` successfully but then set `snapshot['journal_clear'] = recovery_mode`, which is false for normal POST_START, so `assemble_proof()` invariably rejected even a valid retired v2 quarantine. Corrected local `tools/node104_d091_physical_proof_collector.py` to set clear only after `_journal_state` succeeds; Recovery still reports not cleared without making a false claim. Added focused tests; Linux **39 PASS** (D091, D149, D142). This fix is NOT yet deployed, and the old D148 pin remains archived for recovery. Next: create an exact revised D148 observer pin (versioned, retaining legacy), update D149 routing, rebuild and test a new complete source release and Python 3.11 candidate, then rerun real D145 prepare before any execute. Do not activate stale `daa6bff` candidate: POST_START observer is incompatible with it. Physical actuation untouched, service remains active.

## 2026-11-05 — read-only HA102 RD6018 dashboard

Source/docs implementation commit: `3229f77247758a1c5d093e68a371f2595ef307bf`.
Added `docs/operations/ha_dashboard/rd6018_control.yaml` and its install and
entity-mapping runbook. Installed a separate storage dashboard on HA102 at
`/rd6018-control`; the existing `dashboard-rd6018` remains listed and its
configuration remains readable. HA version `2026.10.4`; WebSocket save and
readback matched the source config exactly. All 19 entity IDs were present in
live `/api/states`; the config uses stock Sections, heading, tile, entities and
history-graph cards, with zero switch/number entities or service actions. The
24-hour Recorder query returned measured battery voltage and measured output
current history. YAML parsed, stock-card/entity checks passed, and the graph is
configured for all 12 section columns. No automated application tests were
run; this stage only changes HA dashboard YAML/docs.

The authenticated HA observation at 2026-11-05 08:05 UTC showed Output mirror
code `1`, HA switch `on`, battery voltage about 14.83 V and measured output
current about 0.23 A. This is **HA-only secondary telemetry**, not fresh direct
ESP proof. Direct Native API access was attempted through the existing
`esp_direct` client but is blocked because the ESPHome API encryption key is
not available in the existing local runtime/secrets. Record **ESP ACCESS
BLOCKED**; do not claim physical pass or act on Output based on HA. No output,
setpoint, lease, battery, service or firmware command was sent.

node104 hands_off and deployment state were not rechecked or changed for this
HA-only task; the previous node104 evidence in this checkpoint is historical,
not current proof. Local `main` contains the dashboard source commit above and
this checkpoint update; `origin/main` has not been changed or pushed. No push
was attempted. A pre-existing untracked `.codex_ha_ui_task.txt` remains
untouched. Next: resolve direct ESP Native API access before any
physical-state verification; dashboard itself is deployed and read-only.

## 2026-11-05 — EFB Recovery adaptive plateau (shadow only)

Operator approved dynamic 90–120 min observation instead of 45 min for EFB 65 Ah Recovery; physically confirmed 24 °C at discussion time. Added pure non-actuating `runtime/charge/evidence/recovery_plateau_policy.py` and unit tests; it does not block plateau detection using the historical `0.004C` tail threshold. First/last 15 min median comparison: <=0.01 A at >=90 min confirms; 0.01–0.02 A continues toward 120 min, then stays inconclusive; >0.02 A means charging progress. No second engine, no production stage binding, no node104 deployment, no hardware actuation. Historical HA current replay confirmed a flat low-current trace around 100–117 min, but temperature/CV continuity was assumed in this read-only replay and is not live safety evidence. Full details: `docs/assistant/RECOVERY_ADAPTIVE_PLATEAU_2026-11-05.md`.

## 2026-11-05 continuation — adaptive EFB Recovery recipe candidate

The 90–120-minute `RecoveryPlateauObserver` is now integrated **in source**
with existing `application/charge_session_tick.py`; it is a bounded
process-local observation, not an independent controller. Pinned EFB
Recovery/Conditioning recipe opt-in (default disabled) and variable metadata
are wired to existing `main_authority` and its established DESULFATION/MIX
stage effects, keeping stage owner, attempts, thermal/communication veto,
and existing voltage/current/safety envelopes. No unpinned behavior change.

Off-line source focused regression **42 PASS, 177 subtests PASS**; the broader
suite stopped at collection due to unavailable `aiogram` / `dotenv`
in system WSL Python. Read-only node104 SSH access attempted but credential
authentication failed; live node104 session/code **unverified**. No deployment
or physical charge changes. Next: restore established project test environment
for full regression, inspect live node104 code and session using the canonical
credential profile, and plan coherent-source rollout without disrupting the
active EFB 65 Ah charge. See
`docs/assistant/RECOVERY_ADAPTIVE_PLATEAU_2026-11-05.md`.

## 2026-11-05 09:35 UTC — node104 guarded MAIN → MIX software fault, source-only repair

Verified fresh pinned-key SSH from HOME-PC WSL: node104 `rd6018-bot.service`
active PID 213548, NRestarts=0, current production source does **not**
contain adaptive recovery plateau. Running EFB 65 Ah Recovery session
reached `Main Charge -> Mix Mode` at 09:35:08 UTC by old decision
`main_tail_hold_complete_recovery_mix`. The canonical writer threw
`GuardJournalError(ineligible_charge_stage)`, then the generic data_logger
handler triggered emergency OFF. Output OFF was verified by node104 at
09:35:16 and lease disarmed at 09:35:18. HA102 at 10:02 UTC confirmed
13.26 V, 0 A, OFF, lease OFF; controller remains active service-wise but
is **not charging**. The persisted canonical document remains MAIN, profile
EFB, 65 Ah, Recovery, with current guard rev 481, no pending operation,
no guard fault; control mode `pb_managed`. Do not restart service or
blindly resume this stale guarded session.

Source-only patch to `main_guard_session.py` and `session_atomic.py`:
allow keeping a previously validated MAIN Guard journal during an atomic
MAIN→MIX continuation, but forbid creating a new journal in MIX, dropping
the existing guard, bypassing pending ratchet work or accepting an unrelated
prior stage. Existing guarded restore admission remains unchanged.

Regression: Windows project Python 113 PASS / 984 subtests, one Windows
directory-fsync specific failure; Linux focused run 117 PASS / 984 subtests,
including guarded session and native recipe parity. Additional owner tests
cover pending guard and growing charging current. Full Linux suite
to be recorded after completion. No node104 source update, service restart,
device setpoint change or output command was made. Detailed incident:
`docs/assistant/RD6018_MAIN_MIX_GUARD_HANDOFF_2026-11-05.md`.

## 2026-11-05 — exact offline MAIN→MIX repair release acceptance

Code commit `372f4ea81c63fae20700eca85bbfa2aed8991ee9` staged offline by
existing node104 source packager; 1,352 files verified against release
manifest. Exact extracted Linux release, with subprocess-capable project
dependency venv: **2,888 PASS, 10 skipped, 5 warnings,
1,673 subtests PASS, zero FAIL/ERROR**, 147.09 seconds. Source-only
`.git` tests skipped normally. This supersedes earlier environment-related
partial/full failures; see incident document for details.

**Not deployed.** Live node104 after software-triggered MAIN→MIX emergency
remains with output OFF, lease disarmed, service active, preserved guarded
EFB 65 Ah Recovery MAIN session. D090 production transaction state and
guarded-session restoration must be reconciled through the existing owner
before an update or restart. No unrequested physical re-energization.

## 2026-11-05 — node104 stage-only after third MAIN→MIX emergency OFF

User explicitly ordered installation and requested dry-run proof. Exact
`372f4ea81c63fae20700eca85bbfa2aed8991ee9` release was previously
validated from source archive: 2,888 tests PASS, 10 skipped,
1,673 subtests PASS, 0 FAIL. This is a full offline regression, not
physical actuator simulation on node104.

Fresh pinned-SSH node104 inspection at 10:48 UTC:
- service active PID 213548, zero restarts, production application unchanged;
- canonical guarded EFB 65 Ah Recovery session remains MAIN, Guard rev 481,
  pending=False, physical output was OFF at last HA check;
- `D090_TRANSACTION.json` still `phase=STARTED`,
  `source_sha=930239c670899e14ccb09154d99baf77df90da10`,
  **candidate_inventory absent**;
- `.deploy_sha=58321a866dd68195bf8264d1d9ebe7c18a60748f`;
- existing D145 entrypoint becomes importable with
  `PYTHONPATH=/opt/services/rd6018-bot/app` but is pinned to
  candidate `d351c208...`, not current `372f4ea...`.

Exact archive, RELEASE_MANIFEST.json and STAGED_OK were transferred by pinned
SSH/SFTP into `/tmp/rd6018-source-372f4ea` on node104, each hash-verified
on remote. This is **stage-only**, not an active source deployment.
No service restart, physical START, setpoint write, session modification,
journal rewrite, or direct app replacement performed. Next production
step must use the existing D090/D145 owner with a new reviewed exact
candidate profile and preimage, not the obsolete D145 source pin. Do
not falsely claim installed. Keep D090 historical evidence unchanged.

## 2026-11-05 11:06 UTC — node104 deployment admission recheck (blocked)

Used pinned-key SSH with `RejectPolicy` and the installed read-only D148/D091
collector before and after the only attempted production-owner operation.
Both fresh direct ESP Native subscriptions identified the expected node and
reported R18 OFF, measured 0.0 V / 0.0 A, lease disarmed and boot quarantine
false; HA matched. Service remained active at PID 213548 with NRestarts=0.
The second proof was acquired after D145 prepare refused. No service stop or
start, actuator command, setpoint write, session edit, D090 edit, or application
replacement occurred. This collector does not expose R16, configured V/I,
OVP/OCP, battery voltage, lease generation/remaining/Modbus age, or all edge
flags; those fields are therefore not claimed as verified in this stage.

Ran the installed D145 `prepare` against `/tmp/rd6018-source-372f4ea`. It
failed read-only in D137 with `durable retirement and verified-OFF identity do
not agree`: the canonical guarded EFB 65 Ah Recovery session is still active in
MAIN, not retired. The run did not reach D138 candidate admission or mutate
state. Existing D090 remains `STARTED`, source
`930239c670899e14ccb09154d99baf77df90da10`, no `candidate_inventory`, and
`.deploy_sha=58321a866dd68195bf8264d1d9ebe7c18a60748f`. Also discovered an
already `COMMITTED` D144 journal for source `9a1f5ea4784dc37b19156c462e36c3b4a3de81c9`;
do not overwrite it. Installed D145/profile/D147/D148 hashes remain pinned to
their existing historical versions, and do not bind the requested `372f4ea`
candidate. The current guarded session cannot be made to look retired, and the
372f4ea release identity/pins must not be rewritten without a complete retest.

Exact code release remains `372f4ea81c63fae20700eca85bbfa2aed8991ee9` with
its prior extracted-release result **2888 PASS, 10 skipped, 1673 subtests
PASS, 0 FAIL/ERROR**. No new code or test run. Repository HEAD at this stage:
`3175ee0ed808d2b771c73cbdc6188c1c0d6ee038`; local main and origin/main were
even before this documentation update. Deployment remains **not completed**.
Next: resolve a reviewed state-preserving admission that accepts and byte-pins
this exact guarded session while preserving every existing D090/D144 owner and
profile boundary, then obtain the complete required Native field set and repeat
the owner preflight. Never resume the session or alter battery protections.
