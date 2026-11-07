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

## 2026-11-05 — D145 software-only voltage admission trim

Code commit `4a567261265fbd74380d2c4674a12895be5c3e79` narrows the existing
D090 validator only when called with `software_release=True` by the canonical
D145 owner. That software-only path no longer requires measured analog output
voltage; it still requires independent HA and ESP OFF flags, fresh typed Native
proof, both source charging currents at zero, disarmed lease, clear boot
quarantine, one physical owner, distinct source nonces, and existing session
policy. All other calls retain the measured-voltage check. No D106,
`TrialOffProof`, physical START, configured-setpoint, OVP/OCP or autonomous
checks were weakened. The existing D145 D147/D148 proof schema did not contain
those configured values or autonomous state in the first place.

Focused regression after the code change: **26 passed, 1 skipped, 17 subtests
passed** (`test_node104_d090_release.py`, `test_node104_d145_entrypoint.py`,
`test_d149_observer_router.py`). Full suite was not rerun for this narrow change.

Fresh pinned-SSH execution of the installed D147 read-only collector on
node104 acquired new direct ESP Native callbacks and independent HA evidence:
Native R18 OFF, Native/HA measured U=0.0 V and I=0.0 A, edge lease disarmed,
boot quarantine clear, one physical ESP identity, service PID 213548. This
collector invocation did **not** report R16, lease remaining, Modbus age,
generation, trip, or configured V/I/OVP/OCP; therefore those values are not
claimed from this read. The persisted guarded MAIN session, historical D090
`STARTED` journal and existing D144 `COMMITTED` journal remain untouched.

**Not deployed; no D145 prepare or service lifecycle operation was attempted.**
The installed D145 entrypoint/profile are pinned to the historical source and
do not admit the new release identity. More importantly, the pinned D147/D148
collector/proof schema cannot establish the still-required R16=0, lease
remaining=0 and fresh Modbus age. Those omissions must be addressed with a
reviewed, versioned observer/profile bound to the same D090/D145 owner before
production admission. Do not add synthetic fields or resume the guarded MAIN
session. No actuator, Output, setpoint, lease or journal writes were made.

Repository state after the implementation commit: `main` is three commits ahead
of `origin/main`; no push performed. The pre-existing untracked
`.codex_install_scope_task.md` remains untouched. Next: extend and pin the
existing D145 read-only proof schema to carry actual typed Native R16, lease
remaining and Modbus-age evidence while dropping only the approved install-only
analog/setpoint/protection/autonomous requirements; preserve all START and
trial checks, then rebuild/retest an exact release before any owner prepare.

## 2026-11-05 12:34 UTC — requested D090/D144/D145 install attempt blocked

Current repository source identity is `f31f134063d46f29cf5bd08205aaba79cf37b7bd`;
local `main` and `origin/main` are equal. The existing local D145 entrypoint is
still immutably pinned to source `d351c208cbf8666f881a4660df6a0b211170e857`,
profile SHA-256 `a2610e4c26c6d2ff6fcd9ac3bc12a1e92aaf0f9d1c49059dcfe5bc2462934e47`,
preimage `9651e979e6394fd53ee373010f845ba00e7ccbbfa85a7a313b95893a0edea444`,
and historical D147/D148 collector hashes. It does not admit the current
source identity. The previously recorded guarded EFB 65 Ah Recovery MAIN
session, historical D090 `STARTED` journal and existing D144 `COMMITTED`
journal were not freshly re-read in this attempt.

Fresh direct ESP Native evidence and live node104 preflight could not be
acquired: the existing pinned SSH profile is unavailable in both the current
shell and Windows runner (`RD6018_D061_PROFILE` absent; no configured profile
file found at the standard locations). No alternate SSH trust path was used.
Therefore live OFF, zero current, lease state and preserved-session identity
are **not freshly verified** in this attempt; state is **ESP ACCESS BLOCKED**.
The installed D147/D148 schema was also previously documented as lacking the
reduced software-only proof's required lease remaining and Modbus-age fields;
that is historical evidence, not a fresh callback.

Focused D090/D144/D145 and pinned-observer regression on this source: **84
tests passed, 1 skipped**, via `python3 -m unittest` (the `python` command is
not installed in this shell). This validates local transaction guards only.
No D145 prepare/execute command could be run on node104, no service or journal
was touched, and no charger/lease/setpoint command was issued. Deployment is
**not completed** and production is left unchanged. No temporary deployment
files were created. Next: restore the already-approved pinned SSH profile and
review a D145 source/profile/observer pin that admits the exact current release;
then freshly collect Native evidence and let the existing owner decide prepare.

## 2026-11-05 12:42 UTC — correction: pinned SSH worked; current prepare blocked

Correction to the preceding 12:34 note: the pinned SSH profile was present and
working. WSL `paramiko` connected with `RejectPolicy` and the pinned
`known_hosts`; no secret values were printed. node104 identity matched the
production node (`rd6018-bot`, machine ID
`d2a570f751e14d8cbc654b5c4559ce24`). The earlier **ESP ACCESS BLOCKED**
statement is withdrawn.

Fresh installed read-only D091 proof at 12:41:46 UTC used the direct ESP
Native subscription and independent HA observation. Both reported R18 OFF,
measured U/I = 0.0/0.0, lease armed=false, boot quarantine=false, one physical
node owner, and native sensor states fresh; service PID 213548. A separate
read-only subscription through the installed `ESPHomeTransport` then captured
the full mapped Native inventory at 12:44:59 UTC: device
`timspb.rd6018-pb-recovery-v2` / `2.3-ha-canonical`, `rd6018-controller`,
`esp01_1m`, device ID 0. Fresh callback ages were 0.04–0.96 s. R18
`output_state_code_v2=0`; measured U/I `0.0 V / 0.0 A`; battery `12.96 V`;
configured V/I `14.82 V / 1.23 A`; OVP/OCP `16.7 V / 12.0 A`; R16
`protection_status_code=0`; autonomous=false; lease armed=false, generation
61, remaining 0 s, TTL 900 s, Modbus age 2.469 s; trip=false and boot
quarantine=false. The detailed D106 projection still failed closed because its
autonomous-field type expectation is `SensorInfo`, while the actual fresh
Native entity is correctly typed `BinarySensorInfo`.

Read-only persisted state remains the guarded EFB 65 Ah Recovery session in
`Main Charge`, trace `e66a2003…`, Guard revision 481. The persisted guard
snapshot still says `last_output_on=true` (no pending proposal/fault), while
the physical Native read says OFF. This mismatch is not repaired or
overwritten. The clear/retired quarantine record identifies a different
session. Existing D090 remains `STARTED` (`930239c6…`, no candidate inventory;
journal SHA-256 `030f0b7a…`), and the prior D144 journal remains `COMMITTED` for
source `9a1f5ea4…`; neither journal was changed. The existing `.deploy_sha`
marker still contains `58321a866dd68195bf8264d1d9ebe7c18a60748f`; it is a
legacy marker, not proof that installed bytes match one source commit.

Ran the ordinary installed D145 `prepare` as root through pinned SSH using the
already staged `372f4ea` candidate path. It reached D142/D137 and stopped with
`durable retirement and verified-OFF identity do not agree`; it did not reach
fresh proof collection or mutate production. Installed D137 SHA-256 is
`c421675c…` and lacks the newer preserved-guarded-session branch. The newer
local D137 branch also requires the persisted MAIN Guard to record
`last_output_on=false`, which the current session does not. Therefore the
fresh physical OFF sample does not authorize a safe state-preserving service
restart. Installed D145 SHA-256 is `5f751ff8…`, pinned to historical D146
source `d351c208…`, not repository HEAD.

Focused D090/D144/D145/D149 tests on current source: **50 passed, 1 skipped**.
Packaged exact HEAD `f31f134063d46f29cf5bd08205aaba79cf37b7bd` with the existing
offline packager at
`/tmp/rd6018-release-candidate-20261105/release-f31f134063d46f29cf5bd08205aaba79cf37b7bd-2i7w2me0`;
manifest, archive and stage marker were created locally. This artifact has no
matching D145/D146 production profile and was not transferred or installed.
After prepare refused, a new D091 Native/HA read again reported OFF and zero
U/I; service stayed active at PID 213548 with NRestarts=0. No service
stop/restart, session/journal edit, actuator command, lease write, or setpoint
change occurred.

Deployment is held on the exact source/profile mismatch and the persisted
Guard OFF mismatch. Do not rewrite profile pins, quarantine, session, guard,
D090 journal or committed D144 history to manufacture admission. Repository
implementation HEAD remains `f31f134063d46f29cf5bd08205aaba79cf37b7bd`;
local `main` and `origin/main` are even. Focused results are not a full-suite
or deployment pass. Next: reconcile the existing session through its owner so
its durable Guard state truthfully records OFF while preserving the session,
then build/review an exact source-paired D145/D146 profile before another fresh
prepare.

## 2026-11-05 — D137/D142 guarded-MAIN OFF preflight implementation

Exact implementation commit: `cc612fe98206e72714b64510b7928a40abdfada5`
on short-lived branch `fix/d145-guarded-main-admission` (parent
`d131ad7bbab1f97f1a012298db79aee1bd78700f`). Local branch is **1 commit ahead
of origin/main**; no push or integration has occurred. The pre-existing
untracked `.codex_bootstrap_fix.md` is preserved and excluded from the commit.

D142 now collects and validates fresh D091 Native/HA OFF evidence before
reading D137/D138 preimage state. A sealed guarded MAIN snapshot may retain its
historical `last_output_on=true` only when that same D091 proof is fresh, bound
to the live service PID, independently OFF/zero-U/I, lease disarmed, boot
quarantine clear, one physical owner, and nonce-distinct. D137 validates the
persisted snapshot rather than `read_guard()`'s restart-normalized in-memory
value, binds the D091 OFF reconciliation into the preimage digest, and keeps
the session, guard, quarantine and historical D090/D144 records byte-for-byte.
All original guard identity, hash, revision, capacity, stage, pending/fault,
retirement and service checks remain. The installed guarded restore path still
requires a separate Native pre-ON reconciliation and armed lease; ordinary
Output enable remains latched. No auto-START or setpoint authority was added.
The old D145 profile/source pin `d351c208…` was not modified.

Software evidence at this code HEAD: `compileall` passed before the final
strict-type-only D137 tightening; the changed modules/tests then passed
`py_compile`. The focused D137/D138/D142/D143/D144/D145/D149, MAIN pre-ON,
guarded restore and startup admission suites passed **103 tests, 34 subtests**.
An ambient full `unittest` invocation was interrupted without a summary. A
full pytest attempt stopped at the existing D061 exact-source manifest digest
under the Windows-translated working checkout; it reported 198 passed, 2
skipped, 24 subtests and one collection/setup error (`untrusted exact-source
manifest`). This is not a source failure or full pass. Run the full suite from
the exact Git archive with the isolated dependency environment.

Fresh pre-change node104 evidence was acquired at 2026-11-05 13:15 UTC (D091)
and 13:20 UTC (full direct Native subscription plus independent HA): service
PID 213548; ESP `timspb.rd6018-pb-recovery-v2`, `2.3-ha-canonical`, device 0;
R18 OFF, measured U/I 0/0, battery 12.94 V, Vset/Iset 14.82 V/1.23 A,
R16=0, OVP/OCP 16.70 V/12.0 A, autonomous=false, lease disarmed/generation
61/remaining 0 s/TTL 900 s, trip=false, boot quarantine=false, Modbus age
5.445 s. Native callback ages in the full read were below 1 s and HA agreed.
Persisted guarded EFB 65 Ah Recovery MAIN session/revision 481 and old D090
`STARTED` plus prior D144 `COMMITTED` were not modified. No service or
hardware command was issued. These observations are historical at checkpoint
time and must be reacquired before production phases.

**Not deployed.** Remaining before actual D144 activation: build an exact
source-paired D145 profile for the candidate without editing the historical
profile, build the matching D138 source tree and Python 3.11 venv stage, test
the exact archive and temporary-root owner path, then invoke that exact staged
D145 candidate entrypoint outside live `app/` under the canonical D090 root
lock. Production prepare must pass fresh proof and preserve exact session and
legacy journals before execute. After restart, verify installed source SHA,
service health, direct Native R18 OFF and lease OFF; do not start or change
setpoints. Update checkpoint again with the final deployment result or exact
owner refusal.

## 2026-11-05 — D145 preimage identity separation

Implementation follow-up separates D090's static installed `app/` inventory
pin from D137's fresh, nonce/timestamp-bound physical and session preimage.
D142 now forwards the actual per-run D137 digest into D138; D144 checks the
static D090 app inventory after D091 has first validated Native/HA OFF. This
does not change the old D145 profile or persisted state. Added regression
coverage; focused result 40 passed, 5 subtests, and compileall passed.

Exact code HEAD pending commit on `fix/d145-guarded-main-admission`; origin
gap must be recomputed afterward. Node104 remains not deployed and current
physical proof must be reacquired before D145 prepare. Next: commit this stage,
rebuild exact release archive, run the complete suite from the archive, stage
the matching D138 tree/Python 3.11 environment, validate a source-paired
external D145 profile and temporary-root same-owner entrypoint, then acquire
fresh direct ESP Native evidence and run production prepare. Stop if any owner
or recovery invariant does not admit.

A further identity correction keeps the validated D091 timestamp/nonces in the
D137 result record but outside its durable preimage identity hash. D142 still
requires and validates the fresh Native/HA OFF proof before D137, and D144
re-collects phase-specific proof. This makes D144's candidate identity stable
across independently fresh physical observations. Regression: 41 passed, 5
subtests; compileall passed. Exact source packaging/full suite must be rerun.

D145 prepare then exposed a D147/D148 observer distinction: pinned D147 reports
the guarded MAIN session as inactive, while the already pinned D148 recovery
collector truthfully reports `active_session=true` with the same strict fresh
Native/HA OFF proof. D145 prepare and execute now use the existing D148 reader;
D147's pin remains unchanged and D144 already uses D148 for stopped/post-start
phases. Guard-only diagnostics showed revision 481, pending/fault null,
MAIN=true, 65 Ah, historical persisted Output-on=true, and restart-normalized
memory false. No state was changed. The latest successful direct Native proof
reported OFF/0 U/0 I, battery 12.92 V, Vset/Iset 14.82/1.23 V/A, R16=0,
OVP/OCP 16.70/12.0, autonomous=false, lease disarmed generation 61/remaining
0/TTL900, trip/quarantine false, Modbus age 1.87 s; D091 independently agreed.
Code stage is focused-tested only (45 tests, 5 subtests); complete suite and
new exact source archive remain pending.

Two D145 prepares both passed D148/D142 and preserved MAIN rev481 without
resume authority. Their candidate IDs differed because D138 included fresh
D091 timestamp/nonces. D138 now omits only this transient proof subrecord from
the stable candidate identity digest while returning it in evidence and still
binding candidate source/venv plus durable session/Guard identity. Focused
D137/D138/D142/D144/D145: 51 passed, 5 subtests; compileall passed. Full exact
archive suite and repeat prepare identity check remain to run.

## 2026-11-05 — exact candidate and repeated D145 admission

Exact code source SHA: `d2aa2a53b8423292ba3abbbdd3261a73f6b2089a`. It is a local
commit on `fix/d145-guarded-main-admission`; local/origin gap to recompute after
this checkpoint commit. The pre-existing untracked `.codex_bootstrap_fix.md`
remains untouched. The exact Git archive and candidate full suite passed
**2,904 PASS, 9 skipped, 1 archive-only fixture deselected, 1,677 subtests**;
compileall passed. Candidate archive SHA256 is
`68e35a1ec0819fa113aa347dea8b0d1e03f71a16fd9008c6cc4b19f12ea21c0c` and D138
manifest SHA256 is
`f93737d9a5cb5eba2623956e28fad79e9668cc1d04b8253c86525f1f7792abb2`. Node104
staging contains 1,352 exact source files and a Python 3.11.2 venv with clean
`pip check`.

A new external source-paired D145 profile pins the measured old `app/`
inventory (`b1f4db27e7d70f03f2f3197f3a042be39b6bd969614bc4a8869c41f87d0d7a15`);
the old d351 D146 profile remains byte-for-byte untouched. D145 prepare uses
existing pinned D148 for the state-preserving proof. Two separate fresh D091
prepares passed under the same D090 lock and returned stable candidate identity
`39407c15c850ecaeff1e8d2261c7d989b8b5be6ab2d4be9bd4307ab69e5af976`. Guard
rev481, capacity 65 Ah, pending/fault null, historical Output-on true, and no
auto-resume authority are preserved. D144 transaction slot 2 and its backup/
rename paths are unoccupied. Fresh direct Native and D091 report R18 OFF,
measured U/I zero, battery 12.92 V, Vset/Iset 14.82/1.23 V, R16=0, OVP/OCP
16.70/12.0, autonomous false, lease disarmed/generation61/remaining0/TTL900,
trip/quarantine false, Modbus age 5.36 s; Native callback ages <0.5 s and HA
agrees. Next: acquire another fresh direct Native read, execute exact staged
D145 through the same D090 lock, then verify exact installed release identity,
healthy service and fresh Native OFF/lease OFF without START or setpoint writes.
Not deployed yet.

## 2026-11-06 — deployment admission stopped on fresh D091 identity failure

The pre-execution direct ESP Native subscription succeeded against the reviewed
device identity `timspb.rd6018-pb-recovery-v2` / `2.3-ha-canonical`, name
`rd6018-controller`, model `esp01_1m`, device 0. The fresh callbacks were
typed Native SensorState/BinarySensorState and <2 s old. R18=0, U=0.0 V,
I=0.0 A, battery=12.92 V, Vset/Iset=14.82/1.23 V/A, R16=0, OVP/OCP=16.70/12.0,
autonomous=false, lease armed=false, generation=61, remaining=0, TTL=900,
trip/quarantine=false; Modbus age=4.206 s. The production service was active
(PID 213548). Immediately after this, the fresh D091 Native+HA collector failed
closed with `ProofError: ESPHome device identity/project does not match
reviewed node`. Therefore exact D145 execute was **not invoked**; no service,
app/venv, D090/D144 journal, Guard/session, or actuator state was changed.
The direct Native observation is not a substitute for failed independent D091
admission. Deployment remains blocked until the installed collector's identity
configuration is reconciled and a fresh D091 pass is obtained. Do not retry
execute from this evidence. Exact candidate source remains
`d2aa2a53b8423292ba3abbbdd3261a73f6b2089a`; full archive suite evidence above
is unchanged. Branch is 7 commits ahead of origin/main; `.codex_bootstrap_fix.md`
remains pre-existing and untracked.


## 2026-11-06 — D145 environment confirmed; candidate rolled back, slot 2 pending

Code HEAD remains `6ef8a85b65dd301c34cfc1ca6ab25b50f8dfe4d1` on
`fix/d145-guarded-main-admission`, 8 commits ahead of `origin/main`, 0 behind.
The pre-existing untracked `.codex_bootstrap_fix.md` and
`.codex_r72_d091_deploy.md` were not touched. No source code or tests changed
in this operational stage; the runbook was updated with the evidence below.

Inspected the exact D145 candidate path. `tools/d142_readonly_prestop.py`
passes `D090_EXPECTED_ESP_VERSION=2.3-ha-canonical`, software-release mode and
state-preserving-recovery mode to its fresh D091 child. `tools/d149_observer_router.py`
also explicitly passes `2.3-ha-canonical`; D091's `2.2-autonomous-authority`
fallback applies only to callers that omit the variable. Exact D145 prepare
passed D091/D137/D138 with stable candidate identity
`39407c15c850ecaeff1e8d2261c7d989b8b5be6ab2d4be9bd4307ab69e5af976`.
Therefore the earlier D091 version refusal was not reproduced via actual D145.
One attempt failed before D091 because the frozen launcher lacked candidate
import paths; a later invocation added 39 bytecode files to the temporary
source stage. Only those `__pycache__` files were removed, and all later
candidate invocations used `PYTHONDONTWRITEBYTECODE=1`; the exact source
manifest then passed. The archive's earlier full test result remains
2,904 PASS, 9 skipped, 1 archive-only fixture deselected, 1,677 subtests;
that suite was not rerun in this operational stage.

After a fresh direct ESP Native identity/OFF read and unchanged D090/D144
preflight, authorized exact D145 execute began slot 2 and swapped in the
candidate, but D144 did not reach COMMITTED. The command output was not
captured, so do not claim a specific execute exception. Durable state is
`D144_TRANSACTION_2.json` phase `STARTED`, transaction
`d8660aa810f04c75aed679f1f3aa4cb1`, source
`d2aa2a53b8423292ba3abbbdd3261a73f6b2089a`, candidate identity `39407c15…`;
`D144_INSTALLED_RELEASE_2.json` is absent. Fresh direct Native and D091
post-start reads reported Output OFF and zero U/I.

Invoked existing D145 recovery under the same D090 root lock. It restored app
and venv exactly to the D144 transaction's `before` inventory and started the
previous service, then returned the exact error
`TransitionError: restored service not stable`. A later read after startup
readiness logs appeared reported `_stable_process(old_source_sha)=true`.
Recovery could not update slot 2 to `RESTORED`; its phase remains `STARTED`, and
its exact backup remains. Do not edit D144 or infer successful deployment.

Final fresh physical evidence, 2026-11-05 17:11:11 UTC, was direct ESP Native
`SensorState`/`BinarySensorState`, identity
`timspb.rd6018-pb-recovery-v2` / `2.3-ha-canonical`, name
`rd6018-controller`, model `esp01_1m`, device 0; callback ages <=0.56 s.
R18=0, measured U/I=0/0, battery=12.90 V, Vset/Iset=14.82/1.23 V,
OVP/OCP=16.70/12.0, R16=0, autonomous=false, lease disarmed/generation
61/remaining 0/TTL 900, trip/quarantine=false, Modbus age=5.006 s. D091 at
17:11:14 UTC independently reported fresh Native and HA Output OFF/0 V/0 A,
lease disarmed, quarantine clear, active guarded session and service PID
218804. Service is active, one bot process, NRestarts=0. The guarded EFB
65 Ah Recovery MAIN session remains revision 481 and unchanged; session SHA256
`b433bd304d22873dcdc5e3402386ca1c78a2b4ba141c8d241fc0dc7cdbac665a`.

D090 remains `STARTED`, unchanged SHA256
`030f0b7aae43402f523bb57f5acd606e3ab2fe4f7c7d4efd40258b40bde8014e`.
Pre-existing D144 slot 1 remains COMMITTED and unchanged SHA256
`b8b64fd8b95261ba80528aa13e838fd5b3085f46a70ceb7371746c932b35a08a`.
D144 slot 2 SHA256 is
`e864c72a8ddb2270776c0457557a4e5c0a1138fc24c8ebe5d37506cda43666e1`.
Current app/venv match slot 2's original preimage, not the d2aa candidate.

Deployment is **not committed**. Exact remaining blocker: D144 slot 2 is
unfinished. The execute exception was not captured, so its failure point is
unknown. The D145 recovery returned the exact one-shot error
`restored service not stable`; the previous service later became stable, but
the owner has no safe resume/commit path for this unfinished ledger. Do not
rerun execute, hand-edit the ledger, or claim d2aa is installed. Next: review
and test bounded post-start readiness handling in the existing D145 owner,
then resolve slot 2 through that same owner. No charger START/ON/setpoint/lease
writes occurred.

## 2026-11-06 — bounded readiness owner fix; recovery still pending

Current source work is local on `fix/d145-guarded-main-admission`; no deployment
or transaction command was issued in this implementation stage. The D090
`SystemdService` now allows up to 120 seconds for positive readiness, polls the
current systemd MainPID, requires exactly one `app/bot.py` owner, NRestarts=0,
active service and a polling log after the current `ActiveEnterTimestamp`, and
fails closed on startup faults, PID changes, service exit, or timeout. D144
candidate and rollback/recovery callbacks now use that bounded owner readiness
method instead of the one-shot private predicate. This fixes the observed
sliding-30-second journal window and covers both successful cutover and restore.

Focused regression: **38 PASS** across D127 readiness, D144 transition/owner,
and D145 entrypoint tests. Cases include 41-second delayed startup, bounded
timeout, stopped service, wrong PID, duplicate bot owner, startup fault/current
start-epoch polling, rollback/recovery, and immutable legacy/D144 records.
Exact code HEAD for this readiness change is
`beab527c2f5413962d3bccd8c140f3a0417dca17`, 9 commits ahead of
`origin/main`, 0 behind. Targeted compileall and `git diff --check` passed. Full
unittest discovery remains in progress on the Windows-mounted checkout after
more than three minutes with no result; no full-suite result is claimed.

Fresh owner-provided read-only D148 observation via the pinned HOME-PC WSL
Paramiko SSH profile (RejectPolicy + known_hosts), 2026-11-05 17:23:02 UTC:
Native and HA both report R18 OFF and measured U/I 0/0; Native sensor state is
fresh; edge lease disarmed; boot quarantine clear; one physical node owner,
service MainPID 218804, active guarded session. This D148 projection does not
report battery, setpoints, OVP/OCP, R16, generation/remaining/Modbus age, or
trip/autonomous values, so none are newly claimed here. No actuator command was
sent. D144 slot 2 remains STARTED pending same-owner recovery; D090 STARTED,
D144 slot 1 COMMITTED, and the guarded session remain immutable. d2aa2aa is not
installed. Next: finish exact-source regression, commit owner readiness change,
then use the authorized existing D145 recovery path with a fresh D148 read and
verify exact old preimage/RESTORED before building a new candidate.

## 2026-11-06 — readiness fix committed; deployment remains blocked

Owner-readiness implementation commit: `beab527c2f5413962d3bccd8c140f3a0417dca17`.
Documentation follow-up HEAD: `530ee534d0f7a6557e6005a150653623b24d2c40`,
branch `fix/d145-guarded-main-admission`, 9 commits ahead of `origin/main`,
0 behind. Focused D127/D144/D145 tests: **38 PASS**. Targeted compileall and
`git diff --check`: PASS. The exact full suite was attempted from a clean
archive. Without dependencies/test environment, 1,636 discovered tests had 234
import/errors and 2 failures. With temporary requirements venv it ran 2,722
tests, 10 skipped, and 21 errors because it was invoked with the wrong cwd and
without `TG_TOKEN`. A corrected cwd + test-only token rerun was stopped after
9 minutes without completion; no full-suite PASS is claimed. Temporary venv
and archive are under `/tmp`; no deployment files were changed.

Fresh pinned HOME-PC WSL SSH read at 2026-11-05 17:29:54 UTC via D091 collected
new direct Native SensorState and HA readbacks: R18 OFF, U/I 0/0, Native fresh,
lease disarmed, quarantine clear, one owner, service PID 218804. D148 separately
confirmed guarded session active. D091 reported `active_session=false`, so it
cannot be used as the state-preserving recovery proof. Installed D106 detailed
observer was attempted read-only and failed closed because its configured
entity type expectation rejects actual current Native inventory types (first
`autonomous_mode`, then configured voltage readback). Consequently battery,
V/I setpoints, OVP/OCP, R16, generation/remaining/Modbus age, trip and
autonomous remain unverified in this latest complete read set. This is an
exact evidence blocker for D145 recovery/deployment under the mandatory Native
first rule; no recovery or execute command was invoked.

The installed D090/D144 owner files remain at their pre-fix hashes; thus the
new bounded readiness logic is local only. Existing D144 slot 2 remains
`STARTED`; D090 `STARTED`, D144 slot 1 `COMMITTED`, and guarded EFB 65 Ah
Recovery session remain untouched. The active old service remains PID 218804
per the latest successful observer, and D148 reported Native/HA OFF with zero
U/I. Do not claim slot 2 settled or d2aa installed. Next work must first fix or
use a correctly typed existing direct read-only collector to capture the full
required current Native field set, then stage the exact source/profile and use
the same D090 lock and D145 owner with bounded readiness to settle slot 2.

Documentation HEAD after the blocker/runbook synchronization is pending this
commit; the code source remains `beab527c2f5413962d3bccd8c140f3a0417dca17`.
The readiness fix is committed but not deployed. No node104 service, app/venv,
transaction journal, session, setpoint, Output or lease write occurred during
this stage.

Final documentation HEAD for this stage: `3e1b4fe65f03bb5320e38cde42c1b95b6b40b158`,
12 commits ahead of `origin/main`, 0 behind before this final checkpoint hash
update. Pre-existing untracked notes `.codex_bootstrap_fix.md`,
`.codex_r72_d091_deploy.md`, and `.codex_r72_readiness_fix.md` were left
untouched.

## 2026-11-06 — same-owner recovery completed with bounded readiness

Correction to the prior deployment hold: the requested reduced software-only
admission is supported by the existing D145 path. The current direct Native
proof was obtained first from a fresh typed `SensorState`/
`BinarySensorState` subscription to device 0, identity
`timspb.rd6018-pb-recovery-v2` / `2.3-ha-canonical`, name
`rd6018-controller`, model `esp01_1m`. Callback ages were <=3.47 s:
R18=0, measured U/I=0.0/0.0, R16=0, lease armed=false, generation=61,
remaining=0 s, lease tripped=false, boot quarantine=false, autonomous=false,
Modbus age=3.205 s. The D148 Native+HA observation independently reported
fresh Native state, HA and Native R18 OFF, measured currents 0/0, lease
disarmed, quarantine clear, exactly one physical node owner, and the guarded
session active. Voltage, programmed setpoints, OVP/OCP were not used as
software-update admission conditions. D106 remains a read-only observer with
an entity-type mapping defect; it was not needed for this proof.

Used the exact existing D145 slot-2 bootstrap/profile and D090 owner lock.
Only its two temporary recovery modules were replaced with the exact committed
bounded-readiness files from `beab527c2f5413962d3bccd8c140f3a0417dca17`;
the production app was not directly edited. D145 verified the STARTED slot-2
identity and backup, collected a fresh state-preserving D148 proof, restored
the exact recorded app/venv preimage, restarted the old service, and waited
for bounded positive readiness. D144 slot 2 is now `RESTORED`, transaction
`d8660aa810f04c75aed679f1f3aa4cb1`, journal SHA256
`2a278823e0b5d19a10334f2f0a4763b182d41e7bbf0a0de285754987bb5afdc9`.

Post-recovery, the service is active at PID 219592 with `NRestarts=0`; the
existing D144 readiness callback accepted the service only after its current
start-epoch `Start polling` and `Run polling for bot` entries. Fresh direct
Native callbacks again reported R18=0, U/I=0/0, R16=0, lease disarmed,
generation=61, remaining=0, trip/quarantine/autonomous=false, and Modbus age
0.703 s; max callback age was 3.47 s. Fresh D148 confirmed HA/Native OFF,
currents zero and active guarded session. The EFB 65 Ah Recovery MAIN session
SHA256 remains `b433bd304d22873dcdc5e3402386ca1c78a2b4ba141c8d241fc0dc7cdbac665a`.
D090 `STARTED` remains SHA256
`030f0b7aae43402f523bb57f5acd606e3ab2fe4f7c7d4efd40258b40bde8014e`;
D144 slot 1 `COMMITTED` remains SHA256
`b8b64fd8b95261ba80528aa13e838fd5b3085f46a70ceb7371746c932b35a08a`.
The installed `.deploy_sha` remains `58321a866dd68195bf8264d1d9ebe7c18a60748f`.
No START, Output enable, setpoint, or lease command was sent. No state,
Guard, D090, or slot-1 journal was edited.

The only code change in the recovery runner was the already committed
readiness fix (`beab527c2f5413962d3bccd8c140f3a0417dca17`); its focused 38
tests, targeted compileall, and `git diff --check` remain the available
validation. The earlier d2aa candidate full-suite result remains 2,904 PASS,
9 skipped, 1 archive-only fixture deselected, 1,677 subtests; no full-suite
PASS is claimed for beab. The software update itself remains pending: next
stage an exact source-paired beab candidate, run the existing D145 prepare,
then execute under the same owner only after fresh direct Native + D148 proof.
Current production remains the 58321a preimage until a D144 COMMITTED record
and exact installed SHA are verified.

HOME-PC WSL task prompt files `.codex_bootstrap_fix.md`,
`.codex_r72_d091_deploy.md`, `.codex_r72_next.md`, and
`.codex_r72_readiness_fix.md` were removed after use. Recovery-only `/tmp`
staging had bytecode caches removed; it is transient and not production source.

## 2026-11-06 — software-release proof scope aligned; exact target advanced

The D145 software-release path still read and required output voltage and the
autonomous-mode entity through shared D091/D142/D137 code. This conflicted
with the explicit software-only admission already given. The previous local
beab profile/archive was therefore superseded before any transfer and its
profile artifact was removed. No candidate bytes were installed.

Code commit `9d1aa22243904bc7f9b80f2ae128fc7fc48e193e` now makes the D091
software-release collector subscribe only to fresh typed Native R18/current
callbacks and independently read HA R18/current; it skips voltage and
autonomous-mode identity entirely for that mode. Ordinary D091 callers retain
their existing voltage/autonomous checks. D142 invokes the explicit
software-release validator, whose proof permits voltage fields to be absent;
D137's guarded-MAIN physical reconciliation binds Native/HA OFF and zero
current without analog voltage. Lease/trip/quarantine/authority/fault checks,
freshness, device identity, independent HA corroboration, active guarded
session integrity and no-auto-resume remain enforced. The required fresh
Native R16 and Modbus observations remain a separate direct ESP Native
precheck; they are not fabricated from D091 or D106.

Focused verification after this exact implementation: **59 tests PASS,
1 skipped** across D091 proof collection (22), D142 pre-stop (14), D137
observed preimage (14), and D090 release validation (9); `py_compile` and
`git diff --check` passed. No full-suite PASS is claimed for this new source;
the earlier d2aa exact archive result remains 2,904 PASS, 9 skipped,
1 archive-only fixture deselected, 1,677 subtests. The code source to stage is
now exactly `9d1aa22243904bc7f9b80f2ae128fc7fc48e193e`, not beab.

Production remains `.deploy_sha` `58321a866dd68195bf8264d1d9ebe7c18a60748f`,
service PID 219592, active with `NRestarts=0`; D144 slot 2 is RESTORED,
slot 1 COMMITTED, and D090 STARTED is unchanged. The guarded EFB65Ah Recovery
MAIN checksum remains
`b433bd304d22873dcdc5e3402386ca1c78a2b4ba141c8d241fc0dc7cdbac665a`.
Latest post-recovery direct Native proof reported R18=0, U/I=0/0, R16=0,
lease disarmed/generation 61/remaining 0, trip/quarantine clear, autonomous
false and Modbus age 0.703 s; D148 independently confirmed Native/HA OFF,
zero current and active session. Obtain a fresh direct Native + D148 proof
again immediately before any D145 execute. No START, Output enable, setpoint,
or lease write occurred.

Next: stage exact 9d1aa source and Python 3.11 dependencies, generate a fresh
source-paired D146 profile against app preimage
`b1f4db27e7d70f03f2f3197f3a042be39b6bd969614bc4a8869c41f87d0d7a15`, and
use the existing D145/D090 owner for prepare and any later D144 transaction.

## 2026-11-06 — exact 9d1aa source/profile prepared locally

The beab release profile was superseded and removed before any transfer after
the software-only D091/D142/D137 proof was corrected. Exact source package for
code commit `9d1aa22243904bc7f9b80f2ae128fc7fc48e193e` is now prepared locally:
1,352 files, source archive SHA256
`7a88f39e866405b76760fe0c4ae671aa91f4be86e8c577eb9e6e1fa6593ff663`, D138
manifest SHA256
`da04dd3b68fee2e8566ad6140fade2636d1c476d9bf6b890a90efea8888b3de5`, and
source-paired D146 profile
`docs/operations/evidence/D146_D138_NODE104_PROFILE_9D1AA222.json`, SHA256
`1c55477e693441880b1acfa31d5c2981cfaa775376b080863953d8295aab699a`. The
profile pins restored app inventory
`b1f4db27e7d70f03f2f3197f3a042be39b6bd969614bc4a8869c41f87d0d7a15` and the
existing D147 observer. This exact package has not been transferred or
prepared on node104.

The D091/D142/D137 scope change and tests are code commit 9d1aa; this
checkpoint/profile/runbook follow-up is the current documentation commit.
Production remains `.deploy_sha` 58321a, service PID 219592, D144 slot 2
RESTORED, slot 1 COMMITTED and D090 STARTED; session checksum is unchanged.
Before D145 prepare and again before execute, obtain a fresh direct Native
read of R18/current/R16/lease/trip/quarantine/Modbus and fresh D148 Native/HA
OFF plus guarded-session proof. Use the existing D145/D090 owner and lock.
No actuator write is included in this stage.

## 2026-11-06 — exact beab source/profile staged locally

The recovery stage above is committed as `7b775d4cba62644a4cf0df1aa8550e9f0c6e8d1d`.
Prepared, but have not yet transferred to node104, a source-only D138 package
for exact code commit `beab527c2f5413962d3bccd8c140f3a0417dca17`. It contains
1,352 regular source files, archive SHA256
`c4710ee5e77317b25bb0ceb34b0c05b9d44b49b442d1cb3bbdd72ecc2adfa658`, and
D138 manifest SHA256
`3ded71cbc7fe906985d60fbfef9fca9e4045ad388369381b34ddb8bc39af8183`.
The changed-path inventory has 427 entries and classifies as
`python_control_change`; Python requirement files are identical to the
previous fully tested d2aa candidate. The new source-paired D146 profile is
`docs/operations/evidence/D146_D138_NODE104_PROFILE_BEAB527.json`, SHA256
`47897e673f40f6609c30932ff9d17f62990882a1a498d4ec4d2ec8b6ca78b47a`.
It pins the actual node104 app preimage inventory
`b1f4db27e7d70f03f2f3197f3a042be39b6bd969614bc4a8869c41f87d0d7a15`,
verified read-only against the restored production app after recovery.

This is source/profile preparation only. Node104 still reports `.deploy_sha`
`58321a866dd68195bf8264d1d9ebe7c18a60748f`; D144 slot 2 is RESTORED, slot 1
COMMITTED, D090 STARTED, service PID 219592 active with no restarts, and the
Guard/session checksum remains unchanged. No D145 prepare or execute for beab
has run yet. Next: transfer the exact archive/tree/manifest to the existing
node104 `/tmp` D138 stage, reuse the already validated Python 3.11 dependency
environment because requirements are unchanged, run same-owner D145 prepare,
then obtain another fresh direct Native plus D148 proof before execute.


## 2026-11-06 — node104 9d1aa production installation (D145 / D144 slot 3)

User authorized installation with Output enable and START still prohibited. Exact source commit `9d1aa22243904bc7f9b80f2ae128fc7fc48e193e` was staged on node104 from the prepared D138 archive. Remote SHA256 matched: source `7a88f39e866405b76760fe0c4ae671aa91f4be86e8c577eb9e6e1fa6593ff663`, manifest `da04dd3b68fee2e8566ad6140fade2636d1c476d9bf6b890a90efea8888b3de5`, D146 profile `1c55477e693441880b1acfa31d5c2981cfaa775376b080863953d8295aab699a`. Staged the exact 1,352-file source and an isolated copy of the installed CPython 3.11 venv; `pip check` passed. A separate temporary copy of the existing D145 entrypoint (outside candidate source inventory) was pinned to this exact profile/source/preimage and, after PREPARE, to the observed candidate identity. No new service or owner was created.

D145 `prepare` returned `PREPARE_ONLY_PASS`, candidate identity `0507611e812aefc2d09c77d2a3bb431c0d167764917c87876aaf1f16280bc483`. Fresh pre-execute D148 independent Native/HA confirmed R18 OFF, 0 V, 0 A, active preserved guarded MAIN, disarmed lease, no boot quarantine and one physical owner. D145 `execute` then completed with exit code 0; D144 slot 3 ledger is `COMMITTED`, transaction `606774ae595341978e9577b6ad9ed697`. `D144_INSTALLED_RELEASE_3.json` binds exact 9d1aa source and candidate identity. Service restarted successfully: `ActiveState=active`, `SubState=running`, `MainPID=220987`, `NRestarts=0`.

Post-install source of truth: guarded `state/charge_session.json` SHA256 still `b433bd304d22873dcdc5e3402386ca1c78a2b4ba141c8d241fc0dc7cdbac665a` (unchanged). Fresh D148 after restart again returned independent Native/HA OFF, 0 V/0 A, lease disarmed, quarantine false, active session true, one owner and new PID 220987. Historical `.deploy_sha=58321a...` and D090 STARTED were intentionally not rewritten; installed identity is the D144 slot 3 record. No Output enable, START, setpoint, OVP/OCP, lease or physical charge command was issued. Physical post-install R16 was not separately re-observed in this turn; the latest prior checkpoint reported R16=0. No claim of a full-suite test on exact 9d1aa (focused 59 PASS, 1 skipped at code commit); earlier full-suite applied to predecessor.

## NEXT RELEASE — Telegram orphan MAIN navigation (2026-11-06)

Confirmed after node104 release 9d1aa: an unfinished persisted EFB Recovery MAIN session remains in state/charge_session.json, but the runtime controller is Idle. Telegram /start uses `show_charge_menu=lambda: not app.charge_controller.is_active` in bot.py, so it wrongly offers new charging programs. `runtime/ui/telegram/charge.py` passes only `manual_interrupted` to `build_charge_program_screen`, and `runtime/ui/screens/charge.py` unconditionally lists new chemistry/profile/manual selections. The START guard correctly blocks starting because the persisted MAIN Guard exists; quarantine is independently inactive. Existing `_orphan_stop_token` and confirmation-based `operator_managed_stop` in operator_managed_stop.py recognize and can retire that exact orphan session with fresh verified Output OFF.

REQUIRED FOR THE NEXT RELEASE (do not omit): Use the existing canonical persisted-session/orphan binding as the single navigation source. While an unfinished guarded MAIN exists, hide/disallow new-charge entry/buttons on /start, /modes and charge-program callbacks (including stale Telegram callback buttons); show explicit 'Сохранённая MAIN-сессия — новый запуск заблокирован' and existing confirmed 'Завершить сохранённую сессию' action. Recompute state at each navigation/callback; fail closed on unknown/unreadable preserved-session state, without a second guard or duplicate state machine. Once the existing verified-OFF retirement succeeds, show the normal new-charge menu. Add focused UI/router regressions for orphan, normal idle, active charge, stale callback and post-retirement transitions. Maintain strict Output OFF, no START/actuator or lease writes during development/testing. Do not change stored session/MAIN Guard or relax its safety enforcement just to display UI. Implement and include in the next source release, not a standalone hotfix. Current node104 9d1aa remains active, unchanged.

## 2026-11-06 — EFB75 MAIN->MIX abort: OVP readback timing defect (next release)
Observed node104 `rd6018-bot.service` active PID 220987. At 2026-11-06 03:55:18 UTC the EFB75 Recovery session `fb4c928ef7784c9bb9a76a38c6196c96` entered Mix Mode with reason `main_tail_hold_complete_recovery_mix`. At 03:55:28 `RuntimeSafetyGuard.set_ovp(16.6)` failed the programmed/readback check, triggered verified Output OFF at 03:55:29/03:55:34, lease disarm, and controller stop. About 20 minutes later ESPHome native connection errors to 192.168.1.28:6053 appeared; not proven to be the same root cause. The persisted session remains non-terminal in Mix Mode. The historical OFF confirmation is not a current physical OFF claim.

Code-level defect: `runtime_safety.py` used `_verify_numeric(...)` with default 8 reads / 0.2 s spacing for OVP/OCP/voltage (about 1.4 s between first and last reads), while canonical `*_readback_v2` are independent Modbus-heartbeat mirrors, nominally 5 s, for which current already waits up to 10 s. Therefore accepted programming can falsely fail before its first authoritative mirror. The incident lacks raw actual OVP readback; this explains a concrete failure mechanism, not conclusive proof that RD6018 accepted 16.6 V in that particular event.

Local candidate fix (not yet deployed): `RuntimeSafetyGuard.REGISTER_READBACK_VERIFY_TIMEOUT_S` reuses the existing 10 s finite programmed-register wait for OVP/OCP/voltage; current retains its established wait. It still insists on fresh canonical V2 readback within tolerance, and still fails closed/turns Output OFF if readback never arrives. No recipe, physical guard, voltage ceiling, OVP/OCP limit or live service state has been changed. New regression `tests/test_protection_readback_heartbeat.py` covers delayed V2 OVP/OCP mirrors and permanent OVP failure. Focused offline suite: 55 PASS (protection, runtime safety, managed safety, live transition interlock, hardware trip, OFF containment).

Before deployment: inspect live ESP Native availability and actual physical Output via fresh independent data; preserve the current non-terminal session. Investigate OVP mirror/Modbus diagnostics and ESP network failure separately. No physical START/Output enable, setpoint, OVP/OCP or lease writes are authorized. Also retain existing next-release UI orphan MAIN navigation fix.

## 2026-11-06 — e184468 staged on node104, activation deferred by D137 nonterminal MIX admission

Operator requested installation of OVP/OCP heartbeat-readback fix e18446887d31ce3362a8f0aedf3be557217f257e. Local git tree clean at this SHA. The exact `git archive` was transferred to node104 `/tmp/rd6018-e184468-source.tar`; SHA256 on both ends `2caefc1fb651f51e8f7038d081e7cd33c838b3670d145182c8b6a1ff1aedf0d7` (staging only, not activated). Current installed D144 slot 3 identity remains `9d1aa22243904bc7f9b80f2ae128fc7fc48e193e`, systemd active PID 220987, NRestarts=0; nonterminal saved EFB75 Mix session `fb4c928ef7784c9bb9a76a38c6196c96` SHA256 `2a13504ea96bf7bc127bfacf6e77465dec80cc16198f6dfe602cb2ec100cb6d3` unchanged.

Fresh D148 Native ESPHome plus HA102 read-only observation on node104 returned OFF, 0 V/0 A, disarmed edge lease, quarantine false, one owner (only as-of capture `1793941458.7787688`). Independently invoked the existing D137 read-only preimage observation, which failed with `ValueError: durable retirement and verified-OFF identity do not agree`: canonical D137/D142/D145 supports active preserved MAIN or durably retired sessions, but not nonterminal orphan MIX after аварийное отключение. The MIX session must NOT be silently deleted/retired, and this is not permission to bypass D090/D144 owner or edit production source in place. No service restart, actuator command, or marker rewrite performed. To activate with session preserved, add explicit narrowly-scoped state-preserving nonterminal MIX admission through canonical D137/D142/D145 owner with fresh independent physical OFF at execution and regression coverage; otherwise secure operator-confirmed session retirement under existing verified-OFF workflow, which has not been authorized. Preserve one existing owner and source pins. Current local fix e184468 remains candidate only.

## 2026-11-06 — a6ce87b production cutover on node104 (D145 / D144 slot 4)

Owner-approved release installed and activated via existing D145/D090 owner, preserving unfinished EFB75 MIX session, without START/Output ON or setpoint writes. Exact source `a6ce87bee992768f0cd1398cabccfc59b490cf3d` includes e184468 canonical OVP/OCP/voltage readback heartbeat fix and D137 interrupted MIX admission. Source git archive SHA256 `7bf73ba8ea215160f5506db121870a5619ed1a4563f92ff42f85067c5fa26797`, staged manifest SHA256 `226a4163b0d0e9c5ae48da35c1cad73211a5fb2793d6f202c5c00570eb99ecd9`; D146 profile SHA256 `df1dd4e4a31dd2949252aedb73c5cdca91ef4da1894374d484e3d260762c96e4`; old installed app inventory SHA256 `71d849d980124225354a8977112c91c0dba949c86cd5ef00bd607f5fe3c72162`. Isolated Python 3.11 stage passed pip check.

D145 PREPARE_ONLY_PASS observed candidate identity `f9072c568a87dbe01f015c17a0dd0f45e0d6a37a5eecde8a6792a9fc24fb420e`, preimage `a35dc90c83ef8def88b09bb10224ceed3d21e0262ff24f6518e70530057d8f10`, fresh independent Native+HA OFF with 0 A and disarmed lease; session automatic resume unauthorized. D145 execute completed with exit code 0; installed D144 slot 4 identity records source `a6ce87b`, transaction `4b4739151cbb4f0a8183176d2ab7d39b`. Service after switch active/running PID 223097, NRestarts 0. Preserved state/charge_session.json SHA256 `2a13504ea96bf7bc127bfacf6e77465dec80cc16198f6dfe602cb2ec100cb6d3` (unchanged). Post-start independent D148 Native ESPHome and HA102 both confirmed Output OFF, 0 V, 0 A, edge lease disarmed, single owner at captured_at_epoch 1793945856.115829. This is only as-of evidence, not a claim of permanent physical OFF. Historical D090 marker stays untouched. Temporary staging on node104 removed after verified cutover. Existing next-release Telegram orphan MAIN navigation defect remains planned; this particular release targets OVP-readback and preservation of interrupted MIX across software update. No physical charging test was performed.

## 2026-11-06 — Node104 D145 installation of orphan MIX retirement fix, D149 repair

After operator confirmed Output OFF, Native ESPHome and HA102 D148 read-only evidence independently reported OFF, 0 V/0 A, lease disarmed. Candidate 83684ba (orphan MIX retirement/UI stop binding) was staged but two D145 executions failed at the STOPPED-phase D149 observer. Both failed D144 transactions, slots 5 and 6, were recovered through the canonical D145 `recover` to phase RESTORED; bot was restarted on prior release a6ce87b. Root cause reproduced: D149 routed STOPPED/POST_START through D148 without D090_STATE_PRESERVING_RECOVERY when the saved charge session was absent. D148 then necessarily emitted `quarantine journal is active or uncertain` (journal_clear false in normal mode), despite healthy physical OFF readbacks and a cleared quarantine journal. Corrected D149 to select its state-preserving recovery mode on STOPPED/POST_START; fresh native/HA physical safety, nonce and edge checks remain required. Linux D149 tests: 10 PASS. Commit 062499489c830f33e1573c2ee20773e00620c960 incorporates this correction and previous orphan MIX retirement fix.

First D145 attempt of 0624994 encountered D140 disk capacity block prior to stopping the service. Removed only owned stale staging (`/tmp/d138_stage_4cba9a7`, `/tmp/d138_stage_83684ba`) and orphan candidate-d144-7 (no transaction 7 journal), freeing ~1.4 GiB. Repeated D145 prepare PASS (candidate identity `004764903efb0df3143335c7eb472f8c2d635870c1220d63a7482f972a48cb1f`, composite preimage `ad540bea22e33349101edf70b5ae20f09cb456fc7c3be52dfc3a31bd502d46ce`, active_session false, one physical owner, independent fresh OFF). D145 execute succeeded; D144 slot 7 COMMITTED, transaction `70707293e5294c3f8c213fd22347b33e`, installed source `062499489c830f33e1573c2ee20773e00620c960`, service active PID 224759, NRestarts 0. Telegram polling confirmed in journal at 07:17:58 UTC. Post-cutover fresh D148 at epoch 1793949525.3291903 returned independent HA102 and ESP128 OFF, 0V, 0A, unarmed lease, one owner; these are timestamp-specific readbacks, not continuing physical guarantees. At deployment, `state/charge_session.json` was already absent; deployment did not delete/retire any active session. No START, Output ON, voltage/current/OVP/OCP or lease writes were issued by assistant. Owned staging cleaned afterward, filesystem ~1.1 GiB free. Other unrelated temp stages were not touched.

## 2026-11-06 — offline removal of routine OVP/OCP charge gates (local candidate)

Implemented against code HEAD `a08bd3eeed54385bd28e33e754b4d124d31d58c7`
on `fix/d145-guarded-main-admission`; the local branch was 28 commits ahead
of `origin/main` at inspection. The tracked code/docs/tests below are modified
in the worktree and have **not** been committed. Commit was attempted only
after the focused suite passed, but this environment mounts `.git` read-only
(`fatal: Unable to create .git/index.lock: Read-only file system`). No remote
was contacted. Existing untracked `_codex_remove_ovp_ocp_task.txt` was not
edited or staged.

Normal automatic charge START and stage changes now request/program/verify
Vset/Iset only. `OutputRequest` treats OVP/OCP as optional transaction-scoped
requests; explicit protection requests, including existing Manual paths, keep
their envelope and readback checks. Routine AUTO START and preflight omit both
register writes. MAIN/DESULFATION/MIX stage effects no longer emit those writes.
The MAIN Guard ratchet and guarded pre-ON restore require fresh Native R18,
measured current, Iset, clear typed protection status, existing lease/owner
authority and the durable journal; OCP value/freshness is not a gate and cannot
fault or cause a Guard OCP setter. Desulfation return also changes only V/I.
The preserved Guard snapshot schema/version and restore semantics are
unchanged; no migration or automatic session restart was added. Missing/stale
numeric OVP/OCP no longer faults the active runtime envelope or V/I setters.
Independent hardware trip status, measured voltage/current and temperature
checks, chemistry/absolute V/I ceilings, fail-closed Output transitions and
the 900 s lease remain in force. No software change clears or arbitrarily
rewrites a physical protection register. `docs/V3_PROJECT_RUNBOOK.md` now
states this boundary.

Focused offline validation on Python 3.12: **240 passed, 38 subtests passed**
across MAIN Guard, pre-ON/startup restore, runtime/strict safety, normal charge
effects, SafeOutput, production START and transition tests. Targeted
`py_compile` and `git diff --check` passed. This is not a complete repository
suite or physical acceptance. The earlier focused run had two fixture/test
expectation failures; after correction the final expanded run passed. The
initial standalone `pytest` entrypoint lacked project `sys.path`; validation
used the existing `/tmp/rd6018-task-d142-py312` environment and `python -m
pytest`.

Strict offline scope was honored: no node104/ESP/HA access, SSH, deployment,
service lifecycle, actuator, lease, setpoint or secret operation. Latest
checkpointed node104 record remains D144 slot 7 / source `0624994`, service
PID 224759 active with NRestarts 0, and a timestamped D148 Output OFF/zero U/I
and lease-disarmed observation at epoch `1793949525.3291903`; this task did
not recheck it, and it is not a current physical-state claim. No fresh
hands_off state was established for this offline task.

Next: with `.git` writable, review/stage this exact worktree and commit only
after preserving the green targeted evidence; then run the clean full suite.
Before any later deployment or physical acceptance, follow the live Native
evidence canon and the existing release owner. Do not infer device protection
register values or physical Output from these software tests.

## 2026-11-06 — blocked operator STOP and exact software retirement

At 10:10 UTC the Telegram `operator_managed_stop_execute` callback entered and never returned; multiple operator callbacks remained pending until the bot was stopped at 10:55 UTC. The controller's persisted EFB 75Ah MAIN session `1cdb725aa09140cfa13291e7b82ff188` remained active despite edge safety lease tripped. Fresh independent Native ESPHome and HA102 observations on node104 confirmed R18 Output OFF, 0 V, 0 A, disarmed lease, edge trip latched. With the bot stopped (MainPID=0), the same independent observations were repeated and the exact matching persisted session was retired through the existing atomic `retire_controller_session` writer with verified OFF source nonces bound to the transaction record. Its original contents were retained at `state/charge_session.pre_operator_stop_1cdb725a.json`. After bot restart, MainPID=225428, Telegram polling active, persisted `state=retired`, independent Native+HA OFF, 0 V, 0 A, `active_session=false`. No START, setpoint, lease-arming or Output ON commands were issued. The edge trip remains latched and should not be silently reset.

A local-only follow-up in `runtime/production_runtime.py` removes OVP/OCP idle reset from `_hard_stop_charge`: after verified OFF, retire the session directly, and reject unverified OFF instead of claiming success. Targeted offline regression set passed 52 tests + 3 subtests. This change has NOT been deployed to node104, and the precise wait source of the pre-restart callback stall has not yet been conclusively determined. Do not claim the stall is fully cured until production behavior is verified. Installed node104 source remains 0624994. Current local repo builds on f14fb3e (OVP/OCP reduction).

## 2026-11-06 — node104 software update d71eba3 and recovery of tripped edge lease

After the operator's AUTO EFB75 MAIN session was durably retired, the edge safety lease trip remained latched and prevented new starts. The existing ESPHome `Safety Lease Disarm` button was found in `esphome/packages/rd6018_safety_lease.yaml`: it requires fresh Modbus/output evidence and Output OFF, does not issue Output ON, and clears managed lease/trip. A single guarded normal disarm invocation was made after read-only independent Native+HA OFF, 0V, 0A, disarmed lease, retired charge_session. Initial HA lease-state read briefly still reported tripped, but subsequent direct Native callback independently confirmed `edge_lease_tripped=false`, `edge_lease_armed=false`, `edge_boot_quarantine=false`, no authority/intrinsic fault; no charging start performed.

The D091 software-release proof gate was narrowed locally (commit c80de72) to admit an asserted `edge_lease_tripped` ONLY when both software_release and state_preserving_recovery are true, with independent OFF/zero-current, identity and other edge fault checks unchanged (33 relevant tests PASS). No device-side protection was bypassed. D137 source preimage admission was repaired (commit d71eba3) to accept a sealed atomic retired session with independently witnessed OFF even when the old cleared recovery quarantine journal refers to a different historical incident (21 tests + 5 subtests PASS). This was necessary because exact tombstone identity `1cdb725aa09140cfa13291e7b82ff188` and old historical incident `15d8b26303c548748964b6cae7edf357` are distinct, without altering either journal.

Exact D138/D146 candidate source `d71eba32bfaf7b19075da6db1416acba9895309e` staged. Archive SHA256 `31063ab80279ae332370bdad62ef70a8a938b9d18f8a8a5ab515272d3844ec99`, source manifest SHA256 `f471ac8ddeb56a6f9878a8847281438efec8e4020fdc69e6ac0a2bc567ea6f6c`, source-paired D146 profile SHA256 `0d21dcf045878309733a9a801a3cc41fa9e66144b369b6604cda0304526173c6`, preimage inventory SHA256 `8397440823efa1911a84c0f76b3025f40a83b01b3f6182300a69f63855628f08`; composite state preimage `c8bb86be875a8bea765bdd67f07b614f1b8738126ae1f7b1cb8cdf322861910c`. D145 PREPARE_ONLY_PASS confirmed fresh OFF and capacity. First execute refused capacity before service stop; freed only root/debian pip download caches. Second execute encountered an orphan candidate-d144-8 without transaction journal, which was removed. Final D145 execute completed exit 0 and D144 slot8 `COMMITTED`, transaction `dd1c8f576a304befad6becd799fb2623`, exact installed identity SHA `e853e877787ea6244b13df76eab18fdf6d2f0d5c9f2e394db498b0541de81418`. Bot active PID 225948 NRestarts 0; Telegram polling observed. Fresh post-install D148 at epoch 1793965572.9693155 gave native/HA Output OFF, 0 V, 0 A, `active_session=false`, disarmed lease. Further direct Native evidence at epoch 1793965598.1954732 confirmed trip=false, boot_quarantine=false, one physical owner, no intrinsic fault. Temporary owned stage and input artifacts removed; disk 642 MiB free. No START, Output ON, charging setpoint or edge arm command was executed by the assistant. The graph UI issue and earlier watchdog timeout remain separate topics; they were not solved by this software update.

## 2026-11-06 — EFB60 START OCP trip root cause and offline fix

HA history /api/history/period for 2026-11-06T12:24:20..12:25:45 UTC gives raw `protection_status_code` transition 0->2 at 12:24:48.663119 UTC. Before START, canonical hardware `ocp_readback_v2=1.32 A`, `ovp_readback_v2=14.92 V`, while newly programmed Iset for EFB60 was 6.00 A. Thus the hardware tripped OCP at the lower stale prior-program threshold; this was NOT a fabricated protection status and NOT the 900 s lease. OVP/OCP were deliberately removed from ordinary charge transactions in f14fb3e but RD6018 retains the previous register values. Subsequent read-only state at ~12:44 UTC: OVP=0, OCP=0, protection=0, output OFF. Per RD60xx manuals, 0 disables OVP/OCP; absence of stale thresholds MUST be proved before enabling a new normal charge.

Offline correction in HassClient.turn_on: after fresh OFF/preflight, when current recipe does not explicitly own an OVP/OCP threshold, clear only nonzero retained OVP/OCP to zero using existing setters and independently verify canonical V2 readback within bounded time, *before* Output ON; unknown/unconfirmed readings fail closed. Explicit recipe-owned protection (such as MIX OCP) is not cleared. No continuous MAIN Guard OVP/OCP programming returns. Core regression 48 PASS; expanded START/MAIN/STOP/D091 selection 204 PASS with 14 subtests. No physical ON test was performed by the assistant. Deployment status recorded separately below.

## 2026-11-07 — production release 384516d and node104 cleanup (verified)

The installed RD6018 source on node104 is exactly `384516decb4b44e1cb9324fcf820b23ed445d593`, D144 transaction slot 11 `COMMITTED`, identity `c3df74705a882d24478d6d1caec47c0c51a5d2098a33fce6bd8efe7aaf852ade`, transaction `eb7c5fe4e1cb4951ada4fc4910903d06`. Prior slot 10 committed `1beb4e1ff82aa23850963bf25a7139a3bc8dbab1`. Both installations used the existing D145/D144 owner. Slot 11 had D145 `PREPARE_ONLY_PASS` with independently fresh Native ESPHome + HA Output OFF, zero U/I, no active session and unarmed 900-second lease before cutover. Post-cutover D148 again confirmed those same timestamp-bound physical observations, one owner, and active bot PID 228152, NRestarts=0, Telegram polling. These are historical observations, not a current OFF claim. No automatic START was performed by the deployment.

Root-cause fixes in installed release: old RD6018 protection register OCP 1.32 A persisted across sessions and tripped a 6 A EFB60 START (`protection_code=2` at 2026-11-06 12:24:48 UTC). `HassClient.turn_on` now retires unwanted old OVP/OCP while physical Output OFF, confirms V2 readback before ON and retains explicit MIX protection requests. `managed_runtime_safety.py` now treats OVP/OCP=0 as disabled, not a physical 0 V/0 A limit; positive limits, absolute and recipe ceilings, hardware protection status, output confirmation, temperature and edge lease remain enforced. Bounded shutdown avoids hanging indefinitely during idle service stop. D124 release admission recognizes managed safety modules and safe_output as control changes. Relevant offline tests: 115 PASS for managed safety/START/STOP, plus 66 PASS for D124/control changes; this is not an all-repository physical charge acceptance.

A real EFB 80 Ah `Main Charge` session was subsequently initiated by the operator and was active during node104 cleanup; session ID `7dbfbe4b41814d0f96723ccc55bca8bc`, intended Iset 8 A, Vset about 14.84 V. Post-cleanup runtime logs continued reporting 14.85 V and decreasing current 0.27 to 0.25 A at 23–24°C. The assistant did not initiate or interrupt this session. The D063 voltage-relaxation sidecar remained active but requires eligible SAFE_WAIT for new relaxation points. Do not infer whether charge is currently still active from historical logs: check first.

The operator explicitly requested removal of all old/temporary files from node104, retaining only the working program. The cleanup inventoried and removed 223 old root/temp targets (old D144 backups and venvs, previous release copies, staging/probes) and 3 unused optional D127 candidate files: 226 targets total, about 4.57 GB of file sizes. Current runtime app, venv, .env, state (rd6018.db, charging_history.log, voltage_relaxation.db, persisted session and quarantine/recovery context), working optional/voltage_relaxation, logs/backups and current installed-release identity, D144 transaction 11 plus canonical D090/D144 ledgers were preserved. After cleanup node104 /opt/services/rd6018-bot ~323 MB, /tmp ~84 KB, root disk 5.4 GB available (27% used). Bot PID 228152 and D063 PID 62502 both active, NRestarts 0. Other service emotion-client was not touched. Cleanup did not turn Output on/off or modify live setpoints.

Next engineering priority remains reliable START→MAIN→STOP and measurement acquisition for the adaptive EFB/Ca-Ca mechanism; voltage-relaxation D063 is passive and currently only records when eligible SAFE_WAIT. Review fresh live evidence before any physical work. Preserve 900-second safety lease and physical protection; do not invent new safety layers or confuse this project with Wake Bridge/PCP.

## 2026-11-07 — single accepted-Imin MAIN clock and Telegram countdown (offline only)

Operator confirmed canonical MAIN plateau timer: one accepted current-minimum clock. Whenever the established analyzer confirms a materially lower Imin, the clock restarts. Measurement jitter not accepted as a new minimum does not restart it. If the current remains at/near the accepted minimum for the chemistry hold (EFB/Ca-Ca 3h, AGM 2h by default), the existing MAIN owner evaluates transition using its existing CV, near-target, tail-current, recipe intent, safety veto, temperature and bounded-recovery semantics. For EFB Recovery this permits MAIN -> MIX; do not create another hold clock. An opt-in EFB adaptive plateau recipe retains its distinct explicit authority behavior.

Source correction removes the redundant `apply_continuous_tail_hold` gate but retains its compatibility boundary and cooling state shape. `decide_main_transition` still owns all stage decisions and keeps its `seconds_since_current_min >= required_tail_hold_s` gate. Telegram's MAIN/CV panel shows `Imin ... · до MAIN -> MIX ...` as a countdown based on the same current-minimum timestamp and recipe hold, only while near target and in low-current CV. If hold elapsed, it says awaiting authority decision; outside qualifying CV it does not promise a countdown. Other stages keep existing extrema presentation.

Focused regression and offline dry-run cover accepted Imin reset, 3h EFB / 2h AGM, boundary one second before expiry, invalid tail/unsafe policy not transitioning, normal intent completion, and Telegram panel countdown. These are source-only tests, not physical acceptance. **Do not deploy or restart node104 during the active EFB 80Ah charge**. Last verified running production source remains `384516decb4b44e1cb9324fcf820b23ed445d593` until a separate normal guarded software-release after the live charging session safely ends. No additional independent controller or watchdog was added.

## 2026-11-07 — Telegram UI lifecycle/journal repair (source-only)

Operator screenshot: graph workspace displaced by logs, back navigation delayed, event journal reduced to PREP_SKIPPED. Source repair separates journal message identity from the live graph/control panel, restores a fresh dashboard as the latest bot message after navigation, repairs stale photo/text return behavior and cancellation of obsolete deferred refresh tasks, and applies the same UI lifecycle boundary to canonical menu/detail/help/stats routes. Journal now retains session events, bounds messages and offers page navigation instead of truncating silently. No charge state, actuation, native safety or node104 runtime was modified.

Focused offline unittest matrix: 81 tests passed, including journal, pagination, navigation, menu screens and refresh lifecycle; additional focused graph-restore tests passed (2/2). Expanded legacy callback acceptance matrix did not complete reliably: prior harness background tasks delayed teardown, and a fake callback reached an unmocked Telegram send path. Harness restore is now mocked; do not claim full matrix PASS until independently re-run. No live Telegram/API/physical acceptance claimed. Running node104 remains on last verified installed commit 384516decb4b44e1cb9324fcf820b23ed445d593 until separately authorized release after active charging safely ends. No deployment, restart or hardware commands in this change.
## 2026-11-07 — Telegram UI continuation: non-blocking journal and callback fixture

Following source-only repair 612e3a4, `EventJournalReadService.aread()` dispatches the same existing session-event reader from the asynchronous Telegram snapshot provider using `asyncio.to_thread`; the bot event loop no longer performs the file read inline. The journal page is bounded to two formatted events (Telegram 4096-char message limit), and stale-photo pagination plus source/read exceptions return visible operator feedback rather than silently swallowing a callback. Existing single UI and session authorities remain unchanged.

The legacy offline acceptance fixture was corrected to mock the actual `send_dashboard` and scheduled-refresh boundaries of synthetic callback events; redundant global `asyncio.all_tasks()` cancellation was removed. This affects TEST ONLY, not production Telegram transport or charging control. Latest WSL/Python 3.12 verification from HOME-PC: **83 UI tests passed** (journal, home, navigation, HELP/STATS, charge, details, service, entities, analysis, OFF conditions); modified modules and test compile. Entire callback acceptance matrix is **NOT CONFIRMED PASS**: attempts with isolated synthetic token previously stalled during test teardown, and `asyncio.to_thread` executor in the agent sandbox itself stalled even on a standalone minimal worker example. Do not report physical/production latency acceptance from mocks. No physical node104 access, restart, live Telegram request, deployment or PSU action occurred. New source remains local until post-charge guarded release.
Environment follow-up: an independent HOME-PC WSL/Python 3.12 check outside the Codex sandbox successfully executed "asyncio.to_thread" (returned 1). The observed executor stall is specific to the agent sandbox run, not reproduced by the ordinary HOME-PC WSL invocation; node104 runtime behavior still awaits release acceptance.

## 2026-11-07 — journal truncation root cause (source-only)

A direct defect was found in `charging_log._find_current_session_start_idx()`: the production `SESSION_START` header was followed by `V2_START | PREP_SKIPPED_INITIAL_VOLTAGE=...`, which incorrectly replaced the real session boundary. Consequently Telegram could show only the PREP_SKIPPED line even though the header and preceding session metadata existed in the same log. The boundary now prefers the latest real `SESSION_START`/legacy real `START`; `V2_START` is only the fallback when no real start header exists. The change leaves event production, retention, session/charge authority, and physical control untouched.

Regression covers EFB80 SESSION_START -> V2_START PREP_SKIPPED -> MAIN_CV_HOLD, successive real sessions, and legacy V2-only log fallback. HOME-PC offline validation: **91 tests PASS** across charging_log and 11 canonical Telegram UI modules; syntax checks pass. Source-only; node104 not deployed, restarted or accessed. Full historical callback matrix remains an explicitly open acceptance caveat, not a release blocker invented for the physical charge.

## 2026-11-07 — UI callback and stale journal-page continuation (source-only)

Verified starting HEAD `e11830c74a551c4c6a5d023286535e630317f9a4`; local `main` matched `origin/main` at start (0 ahead / 0 behind). Callback acceptance setup now mocks `_refresh_operator_panel` so synthetic navigation remains within the tested UI boundary and does not read live ESP128 configuration through `OperatorSnapshotProvider`; production snapshot exceptions and logging remain unchanged. The journal screen clamps out-of-range offsets against the current event count, so stale or forged callbacks cannot produce an invalid `1–0` range. Added regression coverage.

HOME-PC Python 3.12 offline UI suite: **100 tests PASS** (`unittest discover -s tests -p 'test_v3_ui*.py'`), and targeted `py_compile` passed. The installed-handler acceptance invocation was attempted using synthetic `TG_TOKEN=123456789:offline-ui-continuation`; an isolated callback scenario reported `ok`, but the Python process remained alive after `IsolatedAsyncioTestCase` teardown and timed out, so the requested full 5/5 acceptance is **not confirmed in this environment**. The offline `tools/ui_callback_acceptance.py` CLI also timed out before printing its handler matrix. Therefore handler uniqueness remains tested for callbacks inside its acceptance cases, but the full matrix evidence and dry-run matrix are incomplete. `git diff --check` passed. A local commit was attempted but Git could not create `.git/index.lock` because `.git` is mounted read-only; changes remain uncommitted in the worktree at source base `e11830c74a551c4c6a5d023286535e630317f9a4`. No push/deploy. Local `main` and `origin/main` were equal at task start (0 ahead / 0 behind). No live Telegram/API, node104/ESP, deployment, service, or PSU access occurred. The last historical node104 source noted above remains a timestamped checkpoint fact only; this task made no current node104 status check. No architecture/runtime ownership changed. Remaining blockers: run full acceptance and CLI in the operator's working HOME-PC WSL environment that exits cleanly; obtain a writable local Git metadata mount to commit this source-only stage. Next work stays UI-only and must preserve the one composition/runtime owner.

## 2026-11-07 — HOME-PC acceptance follow-up (source-only)

The latest HOME-PC Python 3.12 run completed offline installed-callback acceptance: **5/5 PASS** and canonical V3 UI suite: **100/100 PASS**. Offline callback matrix CLI completed after fixing two test-harness defects: awaited async-generator expression in any(), and a bound journal-restore closure escaping the synthetic test through the real Bot API. Test harness now mocks Bot API send/edit/delete methods. Matrix: 102 installed handlers, 67 static-matched, 45 safely dispatched, 57 not exercised by bounded offline scenarios. Uncovered does not equal broken. This supersedes earlier sandbox-timeout caveat. A broad mixed test run exposed one scheduling-sensitive delayed-refresh test; the dedicated two-test suite passes. No production actuator/control changes, deployment, node104 access or live Telegram traffic.

## 2026-11-07 — MIX Imin timer interpretation and Telegram HMI correction

User screenshot (EFB 80Ah, AUTO MIX, 16.51V, 2.23A, CV) showed `Imin 2.18A · 0h25m` with a checkmark. Inspected `operator_hmi.py`, `runtime/charge/strategy/mix.py`, `runtime/charge/runtime/mix_scaffold.py`, `runtime/charge/runtime/mix_finish_hold.py`, and `runtime/charge/strategy/exit_variables.py`. That 25-minute elapsed counter is age since the confirmed current minimum, NOT time remaining to MIX completion; unlike MAIN, MIX CV requires accepted rise Delta I after Imin, and only then the separately pinned two-hour sticky finish hold starts. Standard default delta threshold is max(0.03 A, 30% of accepted Imin), subject to actual recipe/runtime policy. The screenshot alone does not establish accepted Delta or finish hold.

UI presentation-only fix: in MIX CV replace ambiguous `checkmark Imin + clock` with `Imin X A · прошло Xч YYм · ждём Delta I`; do not misrepresent elapsed timer as countdown or change controller/evidence logic. Existing tests updated to assert stage-aware message and real timestamps. HOME-PC offline regression: 37 operator HMI tests PASS, 16 dashboard+refresh tests PASS; Python module compilation PASS. No node104 changes, live Telegram request, PSU/ESP action or deployment. The installed node104 version may still display the old text until separately released. No new UI owner or duplicate timer.
## 2026-11-07 — Telegram MIX status FSM display: extrema -> Delta -> finish countdown

Owner-approved UI-only contract implemented in `operator_hmi.py`. In active MIX CV, before a valid minimum show searching Imin; with accepted Imin, display Imin plus `delta_current_from_min_a` / `reversal_threshold_a` from the existing signal analyzer. In MIX CC, before a valid maximum show searching Vmax; with accepted Vmax display Vmax plus `delta_voltage_from_max_v` / `voltage_reversal_threshold_v` (a positive voltage drop rendered with minus signs). Reaching the numerical threshold without accepted Delta does NOT start a countdown or show confirmed. When the canonical durable `finish_hold_started_at` exists, display the remaining time computed from that timestamp and the existing pinned `MIX_POLICY` finish hold, default 2h; only durable matching-mode finish evidence is labeled confirmed, otherwise explicitly show missing Delta evidence. The MAIN countdown and charge-control/safety semantics are unchanged. No new timer, analyzer, transport or UI service.

HOME-PC WSL Python 3.12 offline results: 41 operator HMI tests PASS; 16 graph/dashboard and refresh tests PASS; 100 V3 UI tests PASS; 5 installed callback acceptance tests PASS. Changes are source-only: active node104 charge was not touched, no deploy/restart/actuator calls, no live Telegram traffic. Production display still needs standard release after physical session. This is an extension to prior MIX Imin-label cleanup.
## 2026-11-07 — MIX CV Delta capped by stage current setpoint (source-only)

User identified impossible threshold: EFB 80 Ah MIX Imin=2.18 A, Iset=2.40 A, standard 30% Delta I=0.654 A implies 2.834 A (> Iset). Authorized rule: target current for CV reversal = min(1.30 * accepted Imin, current stage setpoint). Source owner `SignalAnalyzer` now gets the existing MIX `_phase_current_limit` from the single automatic tick; effective Delta = min(max(0.03 A, 0.30 * accepted Imin), Iset - accepted Imin) when positive headroom >= analyzer absolute-resolution floor 0.03 A. Without sufficient headroom, Delta is unavailable; never invent zero-sized reversal evidence. This applies only to MIX, does not modify MAIN or CC voltage reversal, and still requires the analyzer existing spacing, age, CV voltage/temperature gates. Legacy UI/compatibility `mix_current_delta_threshold` uses the same cap to avoid contradictory telemetry. Example Imin 2.18A, setpoint 2.40A -> Delta +0.22A and target current 2.40A. At the exact current ceiling a physical PSU may transition CV to CC: the CV reversal is not automatically proven and CC Vmax/Delta V remains canonical alternative. This is not a guarantee of completion or permission to raise Iset.

Offline HOME-PC validation: `tests.test_signal_analyzer` 14/14 PASS with new cap/noise-floor/MAIN/CC cases; `tests.test_recovery_policy` and analyzer combined 22/22 PASS; MIX focused group (`test_mix_mode`, `test_mix_legacy_preemption`, `test_mix_delta_time_budget`) 11/11 PASS; canonical legacy support focused test PASS; py_compile of modified production modules PASS. No node104 or physical charger actions; pending guarded future release after charging completion.

## 2026-11-07 — D137 D144 identity fallback for missing legacy marker (source-only)

Current source base at start: `96a1fc294fc56de167f549d71156f82cd349b02a`; `origin/main` matched (0 ahead / 0 behind). Operator supplied fresh D148 Native+HA evidence at 2026-11-07 01:33 UTC: Output OFF, 0 V/0 A, edge lease disarmed, no active session, one owner. This was context for the source-only unblock, not a new live read by this session and not reusable physical authorization.

`tools/d137_observed_preimage.py` no longer requires `.deploy_sha` if absent only when the newest surviving committed D144 slot and its installed identity prove the current release: latest slot is COMMITTED; slot and transaction identity agree; source SHA and candidate identity digest are well-formed; recorded source files and venv match the live installation while generated __pycache__ entries are ignored. Both identity and transaction bytes are hash-pinned and checked for drift during the observation. With a legacy marker present, prior behavior is unchanged. No legacy marker is synthesized; D090 `STARTED` remains historical/read-only; D144 journals are not rewritten; no new owner or authorization is added.

Regression in `tests.test_d137_observed_preimage.py` accepts a slot-11 committed identity in the reported shape and rejects a RESTORED/non-COMMITTED transaction. Focused command `PYTHONPATH=tools:. python3 -m unittest tests.test_d137_observed_preimage tests.test_d142_readonly_prestop tests.test_d144_state_preserving_transition tests.test_d144_owner_binding tests.test_node104_d145_entrypoint`: **63 PASS**. Initial invocation without `PYTHONPATH=tools` had import errors; corrected invocation passed. No physical/server/service/actuator interaction.

Node104 remains at the operator-reported installed source `384516decb4b44e1cb9324fcf820b23ed445d593`, D144 slot 11 COMMITTED. Local release is source-only, not deployed. D145/D146 review: tracked `tools/node104_d145_entrypoint.py` and profile are pinned to older source `d351c208…` and cannot authorize this new candidate unchanged. After commit, stage exact commit tree and Python 3.11 venv; generate/review matching D146 profile and source/preimage/observer pins. Then, only after a new complete direct ESP Native preflight and STOP/session checks, run `python3 tools/node104_d145_entrypoint.py prepare --profile <new-D146-profile> --stage <exact-D138-stage>`, acquire a distinct fresh pre-execute Native proof, and run the same command with `execute`. D145 invokes the existing D090 owner and lock; no separate owner. Preserve original D090 ledger. This source-only note authorizes no future execution.

Commit attempt `git add`/`git commit` failed before index mutation: `.git/index.lock` cannot be created because `.git` is mounted read-only. Current code HEAD therefore remains `96a1fc294fc56de167f549d71156f82cd349b02a` (same as origin/main); four intended files remain modified and uncommitted: `tools/d137_observed_preimage.py`, `tests/test_d137_observed_preimage.py`, this checkpoint, and `docs/V3_PROJECT_RUNBOOK.md`. Unrelated untracked `.deploy_*` files are preserved. `py_compile`, focused 63-test suite, and scoped `git diff --check` passed. Next: remount/provide writable local Git metadata, then commit only those four paths; no push, deployment, or node104 write.

## 2026-11-07 — blocked node104 release after operator started another MAIN session

Operator confirmed previous EFB80 MIX stop. Read-only pinned D148 on node104 at epoch 1794015203.749887 independently reported ESPHome Native and HA102 Output OFF, 0 V, 0 A, lease disarmed, no active session, one physical owner. SSH readback identified service active PID 228152, NRestarts 0, D144 slot11 COMMITTED installed source 384516decb4b44e1cb9324fcf820b23ed445d593. Historical `.deploy_sha` is absent after prior D144 releases; D137 was repaired in source commit 6ee72bb to recognize last surviving COMMITTED D144 identity, checking every original app file and venv against transaction candidate while allowing generated `__pycache__` extras only. Exact current slot11 app: 106 generated cache additions, zero missing source paths and zero changed source paths. D137/D144 focused tests 26 PASS.

Prepared exact source 6ee72bb1b0b4af099e2b2b1436844e97d5bcd2a7 in an OWNED temporary D138 stage `/tmp/d138_stage_6ee72bb1` with 1357 Git-archive files, archive sha256 `99d782d75c13577b5a10db6d2b0a3885cb9400a264240806fbed9a8035442065`, manifest sha256 `d238a138181697d3acdd1a88eaa7f554adf31e84990345638c6b080547749cd3`, staged copied venv `pip check` PASS. No D145 prepare or execute was performed. Read-only new D137 preimage detected a newly persisted active `Main Charge` without canonical guard (`guard_journal_absent`), and correctly rejected the release. Independent fresh Native+HA observations at epoch 1794016376.108186 both reported Output ON, 14.74 V, 0.30 A, lease armed; this is a physical active session and forbids service cutover. Production log establishes previous MIX `operator_verified_auto_stop` at 2026-11-07 11:23:28 local, then NEW `SESSION_START` with `session_reason=User Command` at 11:40:50, followed by MAIN from 11:41:05. Thus not unexplained self-resume of the previous MIX. Do not deploy while this new session is active; do not delete its session or forge a MAIN guard.

Cleanup performed: only owned `/tmp/d138_stage_6ee72bb1` deleted after exact manifest hash comparison; post-cleanup `rd6018-bot.service` active PID 228152, NRestarts 0. Historical D090/D144 journals, active app/venv, `.env`, state, logs and other stages were left untouched; physical output/setpoints/lease were never modified by assistant. Candidate 6ee72bb remains SOURCE ONLY, NOT DEPLOYED. Re-attempt fresh D148 OFF and D145 only after this newly started charge is safely stopped/retired. No background deployment is running.
## 2026-11-07 — node104 production deployment completed, D144 slot 12

Owner explicitly ordered deployment after STOP. Fresh pinned D148 independent Native ESP128 and HA102 evidence before D145: Output OFF, 0 V / 0 A, edge lease disarmed, no active saved session, one physical owner (epoch 1794021909.348363, PID 228152). Existing installed baseline was D144 slot11 source `384516decb4b44e1cb9324fcf820b23ed445d593`; historical D090 `STARTED` ledger preserved. Source `85b70a1642e4dd5629d0f22d4a96ddc770bfed96` includes all previously committed Telegram V3 UI/journal/dashboard and MIX delta fixes, D137 D144 identity support, plus sparse retired D144 slot advancement. D144/D137/owner focused regression 42/42 PASS. No firmware, hardware setpoint, START, Output ON or edge lease write.

Exact Git archive: SHA256 `2560012235e739319d75f3d118451f9ff709afe30a478a2657a907078b958ce3`, 1357 source files. D138 staging manifest SHA256 `c61152a11d41bbcad0feba6c5c2b433b8229991d553589ecc6f5be1a738162bb`; release-specific D146 profile SHA256 `6591589c4fe77803f9b6e275751af9d23bd47023be7b0c552640ab343a0bcd0e`. Python 3.11 candidate venv pip check PASS. Stage file modes repaired from extractor umask to match recorded Git archive manifest; staged-import generated bytecode cache removed with Python bytecode creation subsequently disabled. No production source files were modified outside D145/D144.

Canonical D145 PREPARE_ONLY_PASS: candidate identity `654865a8d29ddd84ebb64874bb6749bd1baceac4a047ed7eec2ceca1e0439c67`, observed composite preimage `d416ff32707c14080fb925b962bab8ae726797c0dc7dc996f46b6cf702186374`, capacity PASS and fresh independently verified physical OFF. D145 execute returned exit 0; D144 slot12 `COMMITTED`, transaction `57e3a41a180a4a4cbc064834462ca161`. Exact installed source `85b70a1642e4dd5629d0f22d4a96ddc770bfed96`; service running PID 229869, NRestarts 0; Telegram aiogram `Start polling` observed at 03:34:05 UTC.

Post-cutover and post-cleanup read-only D148 at epoch `1794022576.0509691`: both ESP128 and HA102 Output OFF, U/I 0/0, edge lease unarmed, boot quarantine false, one physical owner, no active charge session, new service PID 229869. This is timestamped evidence, not a permanent physical-state guarantee. Verified exact COMMITTED transaction and identity before removal of only owned `/tmp/d138_stage_85b70a16`, empty `candidate-d144-12`, and completed duplicate old app/venv copies `d144-backup-12`, `d144-old-12-app`, `d144-old-12-venv`. Durable D090 and D144 ledgers, active app/venv, `.env`, `state` including charge records and SQLite, logs, voltage-relaxation sidecar and unrelated material preserved. Final filesystem 5.4 GiB free, 27% used, bot active with NRestarts 0. Physical charge acceptance of full MAIN/MIX termination is not claimed; software deployment acceptance completed.
## 2026-11-07 — Telegram charge wizard / START panel-order correction

Operator screenshots show EFB intent selection at the bottom immediately followed by an unrelated RD6018 Idle panel, and extra/disordered panel on START confirmation. Root cause was overlapping Telegram rendering owners: `runtime/ui/telegram/charge.py` unconditionally restored L2 while opening the L3 charge wizard, `production_bot_ui.py` independently called `send_dashboard()` after profile/battery/intent selection, and the quick START callback built a dashboard before posting its START result, on top of the existing `PanelLastMiddleware`. This violated the established single UI owner: while charge selection is open the wizard must remain last; after an explicit accepted/rejected START result, the semantic graph/control panel must be restored exactly once after the result.

Fix: remove redundant intermediate dashboard refresh helper/calls and unconditional charge-menu L2 restore. Keep wizard messages current through profile/intent/preview. Remove pre-feedback dashboard build on `v2_quick_start`; the existing `TerminalPanelManager` now uses its canonical `_restore_dashboard_to_bottom` once for `v2_quick_start` / `v2_battery_start`, then adopts that message ID for subsequent updates. No extra UI framework, process, timer, controller, physical command or START route modification. Offline regressions: 101/101 `test_v3_ui*.py` PASS; 27/27 terminal-panel, START-route and callback-acceptance PASS; syntax checks PASS. Source-only pending safe-release decision; physical charge state must be read from fresh D148, not assumed from screenshots. Current installed D144 slot12 source remains `85b70a1` unless verified replaced.
## 2026-11-07 — UI charge wizard hotfix is source-only while user START session active

Following reported extra Idle panel under EFB intent choices and displaced/duplicate panel after confirmation of START, source commit `bd54bd7387fcd88d17c73d17bc8a73d31b29cd25` removes overlapping intermediate presentation owners and makes terminal START callback publish the graph/control panel after feedback. Offline 101/101 V3 UI + 27/27 terminal panel/START route/callback tests PASS; no new runtime authority.

Production node104 read-only inspection at 2026-11-07 03:52 UTC: `rd6018-bot.service` active PID 229869 NRestarts 0; installed source still `85b70a1642e4dd5629d0f22d4a96ddc770bfed96` D144 slot12. Fresh strict D148 OFF gate refused with `ProofError: HA102 physical R18 is not strict numeric OFF`; persisted `charge_session.json` exists. Charge history confirms previous session `operator_verified_auto_stop` at 13:24:17 local, NEW EFB80 User Command `SESSION_START` at 13:38:26, MAIN `V2_START` at 13:38:36, 14.75V/0.26A CHECKPOINT at 13:48:45 local. Accordingly no deploy, restart, OFF/ON or setpoint write was made; active charging is untouched. Next hotfix deployment requires fresh D148 independent OFF and retired/absent active session, then canonical D145/D144 without altering physical session for UI work.
## 2026-11-07 — LIVE incident: Native ESPHome TCP reset during EFB MAIN, V2 readback fail-closed

Owner screenshot showed the V2 safety message `authoritative set_voltage readback V2 is missing/stale` at 14:09 local with 14.74 V / 0.25 A. Read-only node104 `journalctl` confirms 04:09:17 UTC MAIN stable at 14.74V/0.25A, 04:09:38 `aioesphomeapi.connection` `[Errno 104] Connection reset by peer` from ESPHome 192.168.1.28:6053 followed by unavailable `battery_voltage`, 04:09:49 Output OFF requested, 04:09:56 fresh native Output R18 heartbeat independently confirmed OFF. Earlier Nov 6 had repeated resets, ping timeout and `No route to host`; thus network/API-link instability is recurrent, although exact Wi-Fi versus ESP API/remote-reset root cause is not yet established. No evidence that `Imin`/MAIN arithmetic caused the incident. A separate read-only Native/HA snapshot at epoch 1794024727.28 established R18 OFF, 0V/0A, programmed voltage 14.75V and current 8.0A with Native callback ages ~0.4s. Another Native sample at epoch 1794025129.32 showed R18 OFF, 0V/0A, battery 13.41V; persistent `charge_session.json` still held stage `Main Charge`. Do not silently delete/retire it or auto-restart: the safety incident is real and hardware has been OFF. HA uptime entity refers to Nov 6 19:07:44 UTC; no evidence of ESP reboot at the Nov 7 04:09 reset.

Source-level causal defect: `runtime/physical/transports/esp128.py` cleared the subscription cache on connection close then returned from `get_live_values()` after only 0.5 seconds; new Modbus register callbacks may not have populated `battery_voltage`, `configured_voltage`, `current` and protections when managed runtime safety first requested a fresh snapshot. The same transport also normalized missing raw Output R18 to an invented `switch=off`. Narrow transport-only fix: after a detected Native reconnection, wait for the actual fresh configured safety-critical register callback batch, bounded by forty 0.2-second polls (<=8s); if incomplete, return original unavailable/stale metadata to the existing fail-closed safety guard; no source freshness extension, control-route change, watchdog duplication or actuator commands. Missing/invalid R18 is now `switch=unknown`, never physical OFF. The pre-existing 900s edge lease was not modified. OFF verification still requires fresh post-command R18.

HOME-PC WSL Python 3.12 targeted offline tests: 56/56 PASS (`test_esp_home_transport`, `test_managed_runtime_safety`, `test_runtime_metadata_required`), module compile PASS. Tests cover delayed Native register callback batch after reconnect, bounded failure when callback missing, unknown R18 and invalid R18. Additional unrelated pre-existing `tests.test_d123_sprint57_guard_native_evidence` has one standalone failure asserting `physical_ocp_not_confirmed` versus actual `native_iset_matches_canonical_main_guard`; do not represent the combined 63-test suite as passing, and no changes to that domain/test were made. The transport fix is SOURCE ONLY, not deployed to node104. Production remains D144 slot12 source `85b70a1642e4dd5629d0f22d4a96ddc770bfed96`; the Telegram wizard hotfix also remains source-only. No SSH write, service restart, firmware, lease, START/OFF/ON request or physical setpoint command during this incident analysis.
## Link loss policy 300s
2026-11-07 OWNER: Native ESPHome link loss up to 300s must not software-STOP charge. Source guard tracks one monotonic disconnect epoch across partial callback recovery. First Native reconnect waits up to 8s for real registers, then retains outage marker until full fresh readbacks. Managed safety grants 300s for missing/stale evidence within verified Native outage, full blackout gets 300s; outside outages isolated invalid readback still fails. Data logger defers partial charge-controller ticks; hardware watchdog ignores partial Native readbacks during 300s; soft watchdog 360s since last-good for 30s poll margin. Explicit STOP, physical hardware protections and independent 900s edge lease unchanged. WSL offline 72/72 PASS and py_compile PASS. Production not deployed: last verified D144 slot12 85b70a1. No physical actions.

## 2026-11-07 Production activation slot13
2026-11-07 node104 LIVE deployment: D145 PREPARE_ONLY_PASS, D145 execute exit 0; D144 slot13 COMMITTED, installed exact 9692cf37abbb343faff1285b59b03bb668e4c36a, transaction 07a1d7ecce4744bbae5d6b1c328b0ec9. Pre- and post-deploy D148 independently verified ESP128+HA102 Output OFF, 0V 0A, lease disarmed, active_session=false, one owner. Post deployment epoch 1794027078.9520783; service active PID230509 NRestarts0; Telegram aiogram Start polling at 04:50:42 UTC and Run polling at 04:50:43 UTC. Five-minute outage handling is installed. A cleanup attempt of slot13 duplicate folders and owned D138 staging was denied by tool safety, so those copies remain untouched; no claim of full cleanup. Data history, secrets and active code intact. No physical charging test or auto-START.

## 2026-11-07 15:26–15:30 stand local — RD6018 ad hoc monitoring baseline

R7.2 task screenshot confirms 30-minute schedule saved for this chat, next run 15:55 on 2026-11-07. This is separate from built-in ChatGPT automations; execution/delivery at next tick not yet proven. Read-only live node104 check via pinned HOME-PC SSH profile: 2026-11-07T05:26–05:29 UTC. Systemd rd6018-bot active PID230509 NRestarts=0, voltage-relaxation service active; installed D144 slot13 source 9692cf37abbb343faff1285b59b03bb668e4c36a. Fresh independent D148 `collect_live` (not the OFF-only `assemble_proof`) captured 1794029312.9336534: HA102 and ESP128 both Output R18 ON, U=14.77V, I=0.23A; edge_lease_armed=1, trip=0, boot_quarantine=0, configured TTL=900s, active_session=true, journal_clear=true, physical bot owner PID230509. Strict OFF-only D148 command correctly refused because the charger is ON; this is expected during live charge, not a failure of the ongoing charge.

Fresh charge history: new EFB80 `recovery` operator session started local 14:53:10, V2_START MAIN 14:53:25; 15:03:29, 15:14:00, 15:24:30 checkpoints 14.76V, 0.23A, 27→26°C. Saved session mtime 05:29:45 UTC confirms stage=`Main Charge`, v2_intent=`recovery`, programmed voltage=14.76V/current=8.0A; finish hold has not started. Runtime journal after 04:50 release start had no new WARNING/ERROR/Traceback/native connection reset/readback failure/lease fault; one prewritten informational TelegramConflictError message at startup is not evidence of an active conflict, and Telegram polling was observed in release acceptance. Disk 4.6G free, 39% used. No service restart or hardware commands issued. No charge-controller fault or application defect established by this sample. This is a single read-only checkpoint, not proof of future 30-minute run delivery or complete-cycle charge acceptance.
## 2026-11-07 15:56 stand-local — 30-minute charge/health audit and Telegram UI source repair

READ-ONLY PRODUCTION: node104 2026-11-07T05:56:24Z, D144 slot13 exact source 9692cf37abbb343faff1285b59b03bb668e4c36a. rd6018-bot Active PID230509 NRestarts0; rd6018-voltage-relaxation Active PID62502 NRestarts0. Current EFB80 Recovery/Main session (started 14:53 local) persists; last checkpoint 15:56:03 local 14.76V, 0.23A, 26C, finish_timer_start=null. Independent native D148 collect_live (no OFF-only invariant) at epoch 1794031010.4475136: Native and HA both physical Output R18=ON, U=14.77V, I=0.23A; edge lease armed=true, tripped=false, quarantine=false, TTL=900s. No new control faults, native disconnects or restarts over journal range since prior monitoring point. Disk 39% used, 4.6GB free. No remote writes, STOP, START, setpoint, firmware or restart requested.

NEW UI FAULT EVIDENCE: journalctl from 05:32:09–05:32:27 UTC has one Telegram Bad Request 'message to edit not found' and four 'message is not modified' warnings from operator panel refresh. Matches owner screenshot of graph+panel followed by extra text panel, plus 2-event log pagination returning service-only CHECKPOINT. Root causes in source: route-level journal/diagnostics/analysis/entities/off/help/stats restored L2 independently of PanelLastMiddleware, operator_done handler also refreshed separately, stale cached text-panel ID could outrank live graph ID; service-only records were filtered after 2-event page slicing so empty result appeared. Not a charging hardware fault.

SOURCE-ONLY FIX PREPARED: one PanelLastMiddleware owner; read-only routes do not append L2 on entering workspaces; operator_done only acknowledges and middleware performs ONE canonical graph-panel restoration; panel manager prioritizes graph message and retires prior text if refreshed into a new panel; journal filters service CHECKPOINT and V2_START before count/pagination, shows up to 8 concise Russian single-line events, HTML-safe <=4096; source now records analyzer-accepted MAIN_HOLD_START/RESET Imin and MIX_IMIN_UPDATED/MIX_VMAX_UPDATED via EXISTING log_event_sub action (no new clock or stage authority). Milestones appear only after the new source is actually deployed and subsequently recorded; historical past events cannot be invented. Offline WSL Python 3.12: 105/105 V3 UI tests PASS, 77/77 operator dashboard/HMI/panel/nav/journal milestone tests PASS, py_compile PASS. Charger's controller rules, 300s Native-loss grace and 900s lease unchanged. Current node104 still on 9692cf37; do NOT deploy UI-only source into active EFB charge because service restart could interrupt lease. Next authorized safe deployment after session complete, then Telegram live interaction acceptance.

## 2026-11-07 — Graph U/I autoscale source-only fix

Owner screenshot of active EFB80 MAIN graph showed cyan U=14.76V near 15 V and yellow I=0.23A visually indistinguishable from zero because graphing.py forced Y axis to 0..20 whenever a visible-window series was near constant (max-min <0.01V or <0.001A), in both three-pane and twin-axis graph modes. Chart presentation bug, not zero current; independent live ESPHome Native and HA had confirmed 14.77V / 0.23A, Output ON, recorded in prior checkpoint.

Fixed original graphing.py implementation: _visible_axis_limits derives bounds from displayed values, with proportional margin and min span 0.30V for U, 0.10A for I. Stable 0.23A signal axis roughly 0.18..0.28A; stable 14.76V roughly 14.61..14.91V; all-zero current still shows zero, varying startups remain visible. Applies both 3-pane U/I/T and two-axis U/I; existing temperature scaling unaffected. Render tests verify matplotlib axes as well as range math. 8 focused graph tests PASS; 69 related operator/dashboard/graph fallback/graph lazy import/HMI tests PASS; py_compile graphing.py PASS. SOURCE ONLY: no node104 deploy/restart during active charge. Running 9692cf3 still has previous axis behavior until safely updated.

## 2026-11-07 — Node104 U/I autoscale candidate pre-staged, no deployment

Operator ordered the graph auto-scale source release assembled and prepared on host, to install ONLY after the current battery charging session is complete. Exact candidate **034bcee34a5eb199d466f62ee18a640fd323dc88**, with original graphing.py stable-current/voltage axis fix and tests. Source was archived using git archive of that exact commit (1359 files) and staged to node104 **/tmp/d138_stage_034bcee3**. Existing installed production remains D144 slot13 source **9692cf37abbb343faff1285b59b03bb668e4c36a**; service stays active PID230509 NRestarts0, unchanged during preparation. Stage contains source.tar (SHA256 05ac24a8ac4f486c82feefa45c78aab048d8f33560ab8b2000decf7026ffbecb), extracted source tree, copied Python venv, RELEASE_MANIFEST.json (SHA256 4ff0ce3d8e1eaf35014e3b2e44c370e35c5980f9f088621ac96d2b25b69e4533), and RELEASE_HANDOFF.json (SHA256 08aa4ee4e00bd128cc78ab0ab26a900e0ba0f855143a41d5cdd465695b89c551). Local source archive, manifest and release handoff retained at E:\CODEX\rd6018_stage_034bcee3.

Verification on **node104**: all **1359/1359** source files matched manifest SHA256, sizes, exact Git modes (extractor umask differences corrected INSIDE staging only); Python candidate venv pip check PASS; candidate graph autoscale unittest **6/6 PASS** executed from staged tree, using PYTHONDONTWRITEBYTECODE=1. Original HOME-PC related graph/dashboard tests 69/69 PASS. Host after staging: service Active PID230509 with NRestarts0; disk 4.3GB free, 42% used. No D145 prepare/execute, D144 mutation, service stop/restart, hardware action, or setpoint change. The staging source is pinned to 034bcee; this later documentation-only commit does not alter candidate source.

**Post-charge release procedure:** re-verify Native+HA physical Output OFF, lease disarmed, no active session; read fresh D137 preimage after physical stop and create the precise NEW D146 release profile/entrypoint for candidate SHA 034bcee with current D144 slot13 preimage, then normal D145 prepare and execute under existing owner. Do not reuse stale D146 preimage/identity from another runtime. Postflight checks D144 COMMITTED, current source, Telegram polling and physical OFF, only then clean owned stage and duplicate transaction artifacts. Do not remove stage until deployment accepted. No automatic install is scheduled.
## 2026-11-07 16:32-16:34 stand local — scheduled RD6018 node104 check

READ ONLY. Node104 2026-11-07T06:32:21Z: rd6018-bot active PID230509 and relaxation service active PID62502, both NRestarts=0. Installed D144 slot13 source 9692cf37abbb343faff1285b59b03bb668e4c36a. Root filesystem 42% used, 4.3GB free.

EFB80 Recovery session remains in MAIN, started 14:53 stand local. Session updated at 06:32:51 UTC and finish_timer_start is null. Latest history checkpoint 16:27:35 local: 14.76V, 0.22A, 26C; current reduced from 0.23A measured at 15:56/16:17. Independent live read-only D148 collect_live at epoch 1794033161.1019528: ESP128 and HA102 both R18 ON, U14.77V, I0.22A; edge lease armed true, tripped false, boot quarantine false, TTL900s. No new ERROR/WARNING/Traceback/Native connection resets or readback/lease/watchdog faults in selected systemd journal from 05:55Z. No MAIN to MIX transition detected.

Persisted first_stage_hold_since is null but is a compatibility/legacy field. MAIN hold is controlled by signal analyzer confirmed Imin age under apply_continuous_tail_hold; that null alone is not a defect. Analyzer age was not independently queried during this sample. No charge-control or telemetry failure found.

SEPARATE HOME-PC SOURCE WIP: Telegram single-publisher audit has unstaged files, extracted TerminalPanelManager into runtime/ui/telegram/panel_lifecycle.py, leaving telegram_panel.py middleware composition. Test mock paths updated; offline 105/105 V3 UI plus 81/81 panel/operator/start/navigation tests PASS. This is not full architecture acceptance and NOT deployed. Active node104 remains 9692cf37. Staged previously built graph-only release 034bcee3 is distinct from ongoing future UI source, pin exact SHA before any release. No physical actuation or service restart during monitoring.

## 2026-11-07 Telegram UI one-publisher architecture
2026-11-07 Telegram UI architecture: one polling process, but in-process parallel publishers caused duplicate panels. Introduced runtime/ui/telegram/panel_lifecycle.py as sole per-chat lifecycle owner: one current L2 ID, graph adoption/retirement, L3 workspace state, one asyncio lock shared by terminal publication and periodic graph edit, exactly one 60s graph refresh task. telegram_panel.py reduced to middleware/composition. operator_dashboard.py renderer no longer owns task/mutex, operator_hmi callbacks request owner edits. Deleted runtime/production_runtime.py old text dashboard and delayed 60s tasks with 15 calls, no no-op compatibility subsystem; Manual/START/MIX direct publishes removed; /start and notifications use owner. Source only; existing deployed node104 slot13 9692cf37 unchanged. Prior staged 034bcee3 does NOT contain this future UI refactor. Offline tests: 105 V3 UI PASS, 106 combined operator/panel/START/MIX PASS, 18 production/HMI PASS, 3 namespace PASS. Installed callback dispatch acceptance 5/5 PASS with offline token; live Telegram acceptance still pending. No charging changes or node restart.

Final architecture audit: additionally deleted 44 lines of unused runtime.production_runtime._edit_or_send_charge_workspace, a dead L3 Telegram sender that wrote menu message IDs into user_dashboard/chat_dashboard L2 maps. Removed its two obsolete characterization tests; actual /start and panel middleware tests 23/23 PASS. Single active panel owner is unchanged. This is source-only and no production action.

## 2026-11-07 — 60-second in-place Telegram graph + panel refresh preserved during single-owner refactor

User requires the historical convenience: refresh *both* graph and charge parameters automatically every 60 seconds in the SAME Telegram message (no new message, no manual refresh), without duplicate panel owners. The one recurring 60s task now lives in runtime/ui/telegram/panel_lifecycle.py as TerminalPanelManager._graph_tick_loop, idempotently started by start_graph_refresh, and serializes per-chat updates with publish_last and operator graph actions; background edits pause while a submenu workspace owns chat focus. The existing operator_dashboard.py graph renderer updates via Telegram edit_message_media only when a new recorded chart point exists; if the chart cache key is unchanged it now fetches the latest operator snapshot, re-renders caption and buttons, and calls edit_message_caption on the SAME graph message ID. Telegram 'message is not modified' is nonfatal. Neither update path calls send_photo nor deletes/recreates the panel on successful routine refresh. New tests in tests/test_operator_dashboard.py verify live current 0.23->0.22 A changes caption with identical graph samples and message_id=77, and that a new graph sample performs edit_message_media with unchanged ID. 43/43 targeted dashboard/panel/graph tests PASS. SOURCE ONLY during the larger unfinished Telegram ownership refactor; production node104 is unchanged and this is not yet a deployed/live-accepted feature.
## 2026-11-07 Telegram UI single-owner closure: chat binding and callback lifecycle

HOME-PC source WIP only (not deployed). Panel lifecycle owns per-chat panel ID, one periodic 60s graph refresh task, one lock per chat, and active workspace. Telegram message_id is NOT globally unique; old loop incorrectly matched user and chat via identical message_id. Replaced this lookup with explicit chat -> graph-user association, maintained on adoption and retirement. Test with two chats sharing message_id=77 verifies each chat receives its own correct tick; retiring one does not disturb the other.

Graph-range callbacks edit the same L2 graph. They no longer set L3 workspace state, which used to suppress 60-second refresh indefinitely after range change; owner now leaves workspace and adopts existing graph without creating a second message. The Manual successful v2_manual_unbound event used to publish directly and then be classified as workspace by middleware. Removed that direct publish; event is now terminal, so middleware alone restores L2 once. Deleted the unused empty _ADOPT_CALLBACKS mechanism.

Replaced removed monolith-specific stale-message tests with canonical owner tests: stale message is replaced exactly once and old ID retired; Telegram transport failure propagates without false success or deletion. Offline checks in this source state: 105 V3 UI PASS, 49 panel/graph/autoscale/navigation PASS, 28 START/MIX/dispatcher PASS; compilation PASS. Live Telegram acceptance and full installed runtime verification pending. No node104 deploy/restart/control change. Prior staged graph-only SHA 034bcee3 is not the new UI refactor and must not be conflated with a future release.
## 2026-11-07 ? Telegram UI single-owner closure and namespace scan fix

Single-owner source: panel_lifecycle owns per-chat panel ID, one per-chat lock, one 60-second graph refresher and workspace state. Telegram message IDs are chat-scoped, so a two-chat collision is handled by an explicit chat-to-user binding. Graph-range callbacks edit the same L2 and no longer suspend 60s updates; Manual v2_manual_unbound publishes via one terminal middleware path. Empty adopt callback branch removed. Tests of stale message replacement and real Telegram failure now exercise canonical panel owner rather than deleted legacy module. Namespace scanner uses os.walk with pruned .venv and archived worktrees instead of exhausting memory in rglob; namespace tests 3/3 PASS. V3 UI 105/105, panel/graph/navigation 49/49, START/MIX/Telegram dispatcher 28/28 PASS. Source only; no node104 operations. Earlier staged 034bcee3 is graph-only, NOT this future UI release.

## 2026-11-07 Paused D145 blocked
2026-11-07 paused-session deployment audit: D49 UI candidate staged and verified, but D142 read-only preflight fails D137 observed_preimage with guard_journal_absent, because active EFB Main Charge session does not contain main_current_guard_v1. OPERATOR_PAUSE_ON logged at stand-local 17:58:14. Independent HA and ESP Native: Output OFF 0V 0A; edge lease disarmed. Live active_session remains true. D145 prepare/execute NOT invoked, bot PID230509 remains on 9692cf37, no restart or physical writes. Do not fabricate guard or bypass state-preserving admission. Reconsider cutover after session retirement or safely validated guard provenance; stage d49cb6d1 intact.

## 2026-11-07 — Post-charge D49 deployment preflight and external execution block

Operator completed EFB80 charge: at 18:12:41 stand-local, charging history SESSION_STOP reason=operator_verified_auto_stop; state/charge_session.json no longer exists. Physical independent HA102/Native OFF and lease disarmed in last proof. node104 D142 read-only preflight on exact staged source d49cb6d1bb24fa3d2496ca4564aaf1d4ea91fa5b returned PASS_AT_OBSERVATION_ONLY, capacity_pass=true, fresh_d091_off=true, preserved_guarded_main=false. Observed preimage SHA256 0aeef616075d386e8be1dda3c48553a37bf7c3671fb406723dd73d5a18584aed, candidate identity b9be5f6f9188991324372f07fbbfc7d3e9c0999678ecbe332b948d2621f0e981. Guard journal absent blocker disappeared with genuine retired session; no bypass or fabricated state.

D146 exact profile uploaded to /tmp/d138_stage_d49cb6d1/D146_D49_PROFILE.json (SHA256 ff676268e2ce9a5f663ab45280499a1e2971a99ad768cee20d16cc27bee72d0a), with installed app inventory 22e596ba048d9380d057418698c74d0810e5d17230a98cd16b91dd2e52dc8284, 44 changed paths, source and manifest SHA pins, systemd unit SHA 74146a925d8c80a6a240f78877e76e060e674f6928f748db43891e7ff1b0e068, environment SHA 374d4b0decee7d04d0f4358bdcb30a58737c5edd2d3f743cc65d10e56dabc6b3. Canonical profile-loader validation PASS. Existing D145 source-paired entrypoint pinned to these identity values uploaded to the same stage. No new deployment owner or mechanism.

EXECUTION BLOCKER: HOME-PC invocation of canonical D145 prepare was denied by tool safety system before starting. No D145 prepare or execute performed; no node104 restart or hardware operation. Last read-only node104 verification at 08:20 UTC: installed D144 slot13 source 9692cf37abbb343faff1285b59b03bb668e4c36a, service PID230509 NRestarts=0, no active session, 4.0GB free. Candidate stage and profile retained. Do not circumvent tool safety; when execution is authorized use existing D145 prepare then execute under same D090 owner and verify committed release, Telegram polling, Native/HA OFF, persisted data. No second publisher, no additional proof layers.

## 2026-11-07 D144 slot14 installed
2026-11-07 node104 D145/D144 deployment ACCEPTED at service and physical level. Owner retired EFB80 session first; charge_session.json absent. D145 prepare returned PREPARE_ONLY_PASS, fresh_d091_off=true, capacity_pass=true, preserved_guarded_main=false. D145 execute EXIT 0; D144_STATE_PRESERVING_V1 slot14 COMMITTED, transaction be4fce7576844e5c95df1ea8e6aeda15, source d49cb6d1bb24fa3d2496ca4564aaf1d4ea91fa5b, candidate identity b9be5f6f9188991324372f07fbbfc7d3e9c0999678ecbe332b948d2621f0e981. New service PID231800 active from 08:41:27 UTC, NRestarts0, single bot.py polling process. aiogram Start polling and Run polling for bot @RD6018_bot logged 08:41:34 UTC; no active TelegramConflictError (startup INFO contains a generic conflict advisory). Voltage relaxation sidecar PID62502 active, zero restarts. Postflight D148 collect_live: ESP Native and HA independently Output OFF U0V I0A, safety lease disarmed, no trip/quarantine, active_session=false, TTL900s. Disk 3.5 GB free, 54 percent used. No hardware commands. Prior installed slot13 source 9692cf37. D49 stage and release profile retained. Operator navigation, journal formatting, and 60-second in-place message refresh still require live Telegram interaction acceptance, not established by polling.

## 2026-11-07 — MAIN to MIX countdown display polish on frozen UI baseline

Baseline frozen BEFORE modifications. Exact known-good installed UI source d49cb6d1bb24fa3d2496ca4564aaf1d4ea91fa5b is protected by immutable-intent annotated Git tag baseline/rd6018-telegram-ui-fast-slot14-20261107, pushed to owned origin timspb/rd6018_bot. Node104 read-only verification at 09:43 UTC: rd6018-bot.service Active, PID231800, NRestarts0; D144 slot14 installed identity d49cb6d, transaction be4fce7576844e5c95df1ea8e6aeda15, D144_TRANSACTION_14.json present, prior image directories d144-backup-14, d144-old-14-app and d144-old-14-venv exist. No node104 writes or restarts in this sprint; physical controller and established Telegram UI baseline untouched.

Feature-only branch feature/main-mix-countdown-display. Narrow source change ONLY operator_hmi.py (HMI projection) and tests/test_operator_hmi.py; no change to panel_lifecycle, Telegram publisher, SignalAnalyzer, MAIN authority, safety, sample storage, firmware or hardware. Countdown uses accepted analyzer Imin epoch if available, otherwise valid analyzer seconds_since_current_min. A missing, NaN, Inf or negative analyzer clock no longer fabricates a fresh 3-hour countdown: HMI says Imin time unconfirmed. A new accepted minimum resets the displayed countdown through the existing analyzer timestamp; in-place 60-second Telegram refresh recomputes the caption from current time, no new timer. The destination label now respects actual intent: Recovery/Conditioning MAIN to MIX, Normal MAIN completion, AGM or unknown intent MAIN decision. Existing regulator/CV, readback and tail evidence requirements are unchanged. This is operator-facing information, not transition authorization or a guarantee that all independent safety gates have passed.

Regression evidence (Windows repository virtualenv, dummy offline TG_TOKEN): 122/122 targeted HMI, dashboard, panel lifecycle, graph refresh, signal analyzer, MAIN clock/authority tests PASS; 105/105 V3 UI suite PASS; Python compilation and git diff --check PASS. Additional HMI tests exercise missing clock, countdown advancing minute-by-minute without new analyzer sample, normal-vs-recovery destination, and invalid clock. Historical frozen source remains available; new change is NOT deployed, not merged to main. Future installation must use exact new-source SHA, safe retired-session Native+HA OFF proof and existing D145/D144 owner, without modifying or cleaning the slot14 backup before acceptance.

## 2026-11-07 — Modular MAIN countdown owner and mandatory canon

User reaffirmed absolute ban on renewed RD6018 monoliths, scattered settings, duplicate ownership, redundant timers, service layers and ad-hoc proof systems. The explicit mandatory canon is now in AGENTS.md and both V3 architecture contracts plus project runbook (documentation commit b177cab). Every configurable charge duration/threshold belongs to its original typed config/recipe owner; Telegram presentation is consumer-only. Existing slot14 d49cb6d known-good baseline tag remains preserved.

Implemented presentation-only extraction on feature/main-mix-countdown-display: runtime/ui/components/main_stage_progress.py is a 43-line pure formatter responsible only for MAIN countdown wording from supplied canonical duration, accepted analyzer time, readiness, battery chemistry and charge intent. operator_hmi.py calls it; SignalAnalyzer, MAIN authority, charge config, panel_lifecycle.py and the existing single 60-second refresh task are unchanged. It does not create any timer, duplicate policy, actuator or state persistence. The previously completed truthful countdown behavior still handles reset on newly accepted Imin, no fake countdown on missing clock, Recovery/Conditioning versus Normal/AGM destinations. Windows local virtualenv offline targeted suite 122/122 PASS; V3 UI 105/105 PASS; py_compile and git diff --check PASS. Work source-only, NOT deployed to node104; the last verified live slot14 PID231800 was active without restarts. Keep original D144 backup and Git baseline intact. Next: preserve this feature commit on its own branch; make the modularity canon visible on main to all agents and then consider release only after separate physical OFF and D145/D144 admission.

## 2026-11-07 — MIX CV/CC accepted Delta presentation audit and fix, source-only

Scope: user ordered continued work on item 2 MIX indication, explicitly no node104 deployment during charging. Read-only static audit uncovered incorrect UI dependency: after a durable CV Delta accepted, a later live regulator CC caused operator_hmi.py to reject that accepted CV evidence and announce Delta unavailable; the converse CC->CV had same fault. The canonical finish evidence stores the accepted mode independently of current regulator; the controller/SignalAnalyzer retain sole decision authority.

Fixed presentation only: a new small pure read-only runtime/ui/components/mix_stage_progress.py owns the persisted MIX finish-hold label/countdown. It identifies confirmed Delta by durable finish_evidence.mode (CV -> delta I, CC -> delta V), delta_reported and valid accepted reference/delta, not by current live regulator. It displays the remaining hold from existing recipe-owned _effective_mix_finish_hold_seconds and persisted finish_hold_started_at, and labels missing evidence explicitly rather than inventing proof; invalid/future timestamps produce no fake countdown. Existing pre-confirmation live MIX CV Imin/Delta I and CC Vmax/Delta V paths remain in the same read model, with no new clock/publisher/observer/authority or physical call. operator_hmi.py delegates this one existing hold branch; panel_lifecycle.py untouched.

Regressions: 3 new operator HMI tests for accepted CV->CC/CC->CV mode changes and future hold timestamp; 48/48 HMI PASS, 134/134 targeted HMI/dashboard/panel/graph/SignalAnalyzer/MAIN/MIX PASS, 105/105 V3 UI PASS, Python py_compile and git diff --check PASS. Pure source only, still NOT deployed. Frozen known-good node104 D144 slot14 exact SHA d49cb6d1bb24fa3d2496ca4564aaf1d4ea91fa5b and backup must remain untouched until operator explicitly requests a safe deployment. Next sprint: journal event completeness and clear human wording, continuing on isolated source branch.

## 2026-11-07 — Human charge journal pass after MIX presentation fix (source-only)

Audited the existing journal chain: authoritative SignalAnalyzer accepted extrema produce MAIN_HOLD_START/MAIN_HOLD_RESET and MIX_IMIN_UPDATED/MIX_VMAX_UPDATED in runtime/charge/evidence/trace_context.py; existing production runtime log_event_sub writes them to the established charging_history.log, and the canonical journal component filters service CHECKPOINT/RESTORE rows before pagination (8 events/page). Durable V2_FINISH_HOLD_START is recorded by existing runtime/charge/runtime/mix_finish_hold.py; no second journal, telemetry collector, timer, or persistence path is needed. Full live event coverage of a charge cycle remains unproven without a new cycle; do not fabricate past events or equate source audit with physical acceptance.

Found human-factors issue: MAIN_HOLD_START was rendered as if the entire transition hold had definitively started, but the source event only proves the analyzer accepted an Imin epoch (tail readiness and decision gates are independent). Narrow two-string presentation change in runtime/ui/components/journal.py now reads 'Imin принят; отсчёт от минимума' and 'Новый Imin; отсчёт от минимума заново'. Updated existing journal milestone assertions in tests/test_operator_journal_milestones.py. No state transition, safety, output, journal data format, or event producer changes. Tests 116/116 combined operator journal/HMI/dashboard/panel PASS and 105/105 V3 UI PASS, compilation and git diff --check PASS. No node104 deployment per operator instruction; frozen known-good D144 slot14 d49cb6d remains untouched. Next work: continue journal source-to-persisted-event mapping and catalog program parity on HOME-PC, keeping every value at its canonical modular owner.

## 2026-11-07 — 12 native charge recipe variants: ownership catalog audit (source-only)

Audited the canonical native recipe catalog: exactly 3 chemistries Ca/Ca, EFB, AGM x 4 intents normal, recovery, conditioning, diagnostic = 12 descriptive variants, NOT 12 independent controllers. PREP/MAIN/DESULFATION/Recovery SAFE_WAIT/MIX/Final SAFE_WAIT/COOLING/DONE are existing stage-specific production authorities. The diagnostic variants exclude automatic high-voltage DESULFATION, MIX and associated SAFE_WAIT from their advertised stage paths. Native recipe parameters come from strategy-owned VariableSpec declarations; AGM generic MAIN voltage is not editable; MAIN C-rate copies cap at 0.1C; pinned session settings validated through existing native selection and guarded START rather than separate runner. Actual physical stage traversal remains conditional on live evidence and safety, not guaranteed by catalog metadata.

Confirmed catalog ownership mistake: STAGE_OWNERS labelled FINAL_SAFE_WAIT as runtime.charge.runtime.mix_scaffold although existing production stage_authority.apply_authoritative_stage_tick delegates final SAFE_WAIT to runtime.charge.runtime.final_safe_wait_authority.apply_final_safe_wait_authority. Fixed ONLY metadata declaration in native_recipe_catalog.py to the actual existing owner; regression in test_native_recipe_catalog.py checks catalog owner vs production dispatch and exposure for 9 non-diagnostic variants, exclusion for 3 diagnostic variants. No physical runtime code, charge strategy, settings, panel lifecycle, service or hardware modified.

Acceptance: 7/7 focused catalog/default-execution tests PASS; extended native-policy, real-stage, pinned-selection/start, persistence/restore and safe-wait/MIX/desulfation suites 29/29 PASS with PYTHONPATH including repository tests directory. An initial expanded invocation without tests on PYTHONPATH failed module import test_start_transaction_service; rerun with correct test PYTHONPATH passed, no code workaround. Full 12-variant physical battery charge cycles are NOT verified by these tests. Continue separate static parity inventory and preserve node104 D144 slot14 d49cb6d until operator permits deployment.

## 2026-11-07 - Canon: externalize literal configuration and decompose touched monoliths
All meaningful hard-coded numeric and semantic values must belong to one typed config/spec owner; human-facing UI strings reside in focused UI label catalogs. Protocol constants and trivial math are documented exceptions, not arbitrary tunables. Any monolith touched for a feature is incrementally decomposed at the affected boundary, with behavior preserved and redundant logic removed. No new control plane, timer, or duplicate owner. This is a source policy change only; slot14 d49cb6d/node104 remain untouched.

## 2026-11-07 - Journal UI decomposition, source-only
Source commit e403040 on feature/main-mix-countdown-display: moved original 182-line journal owner to journal_filter.py (service-row selection), journal_format.py (read-only rendering), runtime/ui/labels/journal.py (stage/event texts) and runtime/ui/journal_config.py (meaningful presentation limits/page defaults). journal.py keeps stable imports without duplicate implementation. MAIN_HOLD_START and RESET historic messages show concise accepted Imin (RESET uses RE prefix) and hourglass but NO invented live countdown, next-stage destination or persistent reset ordinal; canonical live MAIN countdown still derives from SignalAnalyzer and recipe. Preserved event names/log persistence and Telegram single-owner refresh. Offline Windows venv: 176/176 V3 UI and operator HMI/dashboard/journal tests PASS; compileall PASS; git diff --check PASS. node104 untouched: frozen D144 slot14 production source d49cb6d. Live acceptance and further decomposition of operator_hmi remain pending. Previous source canon commit 93dfdff. No deployment/restart/physical action.

## 2026-11-07 - Incremental operator_hmi decomposition, pure values
Commit 817a632 extracts 38 lines of pure _finite/_on/_regulator/_temperature/_value/_duration from 1382-line operator_hmi.py into runtime/ui/components/hmi_values.py. Existing symbol imports and runtime behavior preserved; no new owner for state or timer, no actuator/config/recipe changes. Windows venv focused HMI 50/50 PASS; extended V3 UI, journal, HMI, dashboard 176/176 PASS; compileall PASS; diff --check PASS. Remaining operator_hmi orchestration/rendering decomposition continues incrementally at semantic boundaries. Frozen production node104 D144 slot14 d49cb6d untouched; no deployment or reboot.

## 2026-11-07 - HMI read-only identity and safety presenters extracted
Source-only commit c6aab5b in feature/main-mix-countdown-display: extracted _battery_label_from_observer/_battery_label_from_manual into runtime/ui/components/hmi_battery_identity.py, and _normal_safety/_operator_telemetry_fresh into runtime/ui/components/hmi_live_safety.py. Removed implementations from operator_hmi.py; existing callers import pure projections and still use original rd6018_telemetry freshness authority. No second telemetry clock, state, logger, lifecycle, or charger owner; unchanged behavior. Focused HMI 50/50 PASS, extended V3 UI/HMI/dashboard/journal 176/176 PASS, compileall PASS, diff --check PASS. Read-only audit flagged hard-coded two-hour copy in legacy adopted MIX observer progress; canonical observer already owns MIX_FINISH_HOLD_S in rd_live_adoption.py, so presentation should eventually consume that owner rather than duplicating numeric semantics. No runtime behavior change in this sprint. Production node104 frozen at D144 slot14 d49cb6d; no deploy/restart/actuator writes. Next: break further HMI presenter boundaries and catalog parity without new owners.

## 2026-11-07 - Adopted MIX hold presenter uses its existing owner (source-only)
Commit 06b7ae1 extracts _observer_progress from operator_hmi.py to runtime/ui/components/adopted_mix_progress.py (pure formatter). The caller passes rd_live_adoption.MIX_FINISH_HOLD_S and current timestamp; observer remains the sole holder of the deadline and safety/actuation authority. Historical copied 2h text removed from the adopted-MIX progress path; 3-hour alternative tested without changing the actual configured 2h observer contract. No new scheduler, duplicated timer, telemetry store, charger setting, or controller. Windows venv focused HMI 50/50 PASS, dedicated duration tests 2/2 PASS, full V3 UI/HMI/dashboard/journal set 178/178 PASS, compileall PASS and git diff --check PASS. Production node104 remains frozen at D144 slot14 d49cb6d, unmodified. Next: inspect remaining operator_hmi read-model and stage-related literal usage, continue program parity and interrupted-session inspection with source-only tests.

## 2026-11-07 - Manual MAIN/MIX progress extraction, source-only
Commit bb5ccff extracts _manual_extrema_status from operator_hmi.py into runtime/ui/components/manual_extrema_progress.py. Read-only formatter consumes current timestamp and canonical MANUAL_MIX_FINISH_HOLD_SEC supplied by caller; MAIN thresholds and hold hours remain from selected recipe. No duplicate timer or charge authority. Source tests: 52/52 focused Manual/HMI PASS; 180/180 V3 UI/HMI/dashboard/journal PASS; 12/12 selected interrupted/restore/native checks PASS, not full physical acceptance; compileall and diff --check PASS. Full physical 12-recipe and end-to-end interrupted restoration acceptance are still pending. Frozen node104 D144 slot14 d49cb6d untouched. Next: inspect interrupted-session recovery path before further HMI extraction.

## 2026-11-07 - Operator action label ownership and recovery source audit
Commit 59cb147 extracts operator action display labels and callback destinations from operator_hmi.py into runtime/ui/labels/operator_actions.py; previous code remains the only keyboard assembly and app action routing owner. Two V3 contract tests now assert the real canonical callback mapping and generated keyboard instead of source-text location. Source-only recovery audit exercised cold-start skip, guarded-main restore hold, restored native recipe parity, terminal restore protection, operator interrupted Manual actions, and restart HA composition. With PYTHONUTF8=1 on Windows (avoids unrelated cp1251 read_text failure), extended 201/201 tests and 23/23 subtests PASS; compilation and diff --check PASS. These are source tests, NOT end-to-end physical restart/live charging acceptance. No added timer, service, safety gate, authorization or recovery path; hardware untouched. Exact production baseline remains node104 D144 slot14 d49cb6d. Next: continue existing UI labels/config semantic ownership audit and validate persisted interrupted-session UI in isolated tests, no production deploy without owner permission.


## 2026-11-07 - One modular operator button decision owner (source-only)
Commit 1aa6d4b consolidates the previously duplicated button eligibility paths from operator_hmi.build_operator_keyboard and OperatorSnapshotProvider into the pure application/operator_button_rules directory. Each focused module has <=46 lines: session.py, external.py, snapshot.py, selection.py, common.py. operator_hmi is now a Telegram renderer of OperatorActionsView rather than another conditional authority; direct legacy calls use the same selector. Explicit interrupted Manual semantic flag (commit 42880af) retains existing callback pair in one row without relying on Russian progress copy. Details and recipe UI strings remain separate in runtime/ui/labels/operator_actions.py. Added tests/test_operator_button_rules.py for AUTO pause, Manual interrupted, HANDS_OFF Output ON/OFF, adopted MIX, containment and snapshot parity. Windows Python UTF-8 run: 296/296 selected UI+ownership+recovery tests PASS, 9/9 subtests PASS; compileall and diff --check PASS. Separate test_operator_navigation_expired_callback remains failing with the same assertion on original HEAD 42880af verified in detached temporary worktree (removed afterwards); no hidden fix or claim of green full suite. No new timer, second UI control plane, safety gate, hardware call, startup service or on-device deployment. Production node104 D144 slot14 d49cb6d untouched. See docs/OPERATOR_BUTTON_RULES.md for rule edit map.

## 2026-11-07 - Interrupted Manual semantic continuity through snapshot
Commit ff5674d repairs a real gap in the unified button selection: `OperatorSnapshot` previously dropped `OperatorHmiState.manual_interrupted`, making the snapshot-based operator panel miss reauthorization/discard. Propagated the *same read-only semantic* via OperatorSnapshot, snapshot_from_mapping, OperatorReadSource.hmi_from_snapshot and existing application/operator_button_rules.selection; generic IDLE stays without these actions. Snapshot.available_actions for interrupted Manual uses the existing shared selector, not a second list. A real provider test verifies state->single HA read->snapshot->actions->HMI->callbacks and the absence of actions for normal IDLE. The stale-callback test now asserts the existing PanelLastMiddleware-only refresh contract instead of requiring a second panel publisher. Offline Windows PYTHONUTF8=1 extended 305/305 UI/navigation/ownership/recovery tests and 27 subtests PASS; compileall and diff --check PASS. This is source-level acceptance only, not physical restart or output command validation. No new scheduler, control owner, timer, hardware access, or production deployment; node104 remains on frozen D144 slot14 d49cb6d.

## 2026-11-07 - Graph/text RD ownership composition consolidated
Source commit 72086bd reuses the same _composed_operator_rows helper for ordinary panel and graph controls instead of duplicating ownership wrapper invocation and release-control filtering. The existing hmi.build_operator_keyboard wrapper chain (rd_ownership_recovery, managed adoption and MIX eligibility) is preserved with no bypass from generic snapshot actions; filtering retains conditional normal-panel versus graph behavior. All three operator_dashboard snapshot/action read sites now pass the same snapshot to OperatorSnapshotProvider.get_operator_actions(snapshot=...), preventing a second HA read that could desynchronize text and controls. New focused test verifies ordinary-IDLE release remains intact while managed-charge release is suppressed. Windows PYTHONUTF8=1 extended test cohort: 306/306 PASS and 27/27 subtests PASS; compileall and diff --check PASS. No new timers, render publishers, safety/charge actions, or physical operations. Node104 D144 slot14 d49cb6d remains untouched; no deployment.

## 2026-11-07 - HMI immutable model and compact textual presentation extracted
Commit 7330b40 moves HmiProcessState/HmiAuthority/OperatorHmiState (immutable dataclass) into runtime/ui/components/hmi_state.py, and pure compact panel projection helpers into runtime/ui/components/hmi_compact.py, with compatibility reexports from operator_hmi.py. Meaningful UI limits COMPACT_TRANSITION_MAX_CHARS, PANEL_HEADING_TARGET_WIDTH and PANEL_HEADING_MIN_GAP now live in runtime/ui/hmi_layout_config.py. The original state builder, production panel and operator navigation remain unchanged in their owner; no added timer, session/charge controller, action rule, transport, or hardware access. Source-only Windows PYTHONUTF8=1 extended UI/operator/ownership/graph/recovery cohort 306/306 tests and 27/27 subtests PASS, compileall PASS, git diff --check PASS. node104 frozen D144 slot14 d49cb6d untouched, no deploy. Next candidate is to decompose details and service-detail presentation from operator_hmi.py into focused read-only presenters while retaining a single Telegram publisher.

## 2026-11-07 - Details and technical service presenters decomposed
Commit 8eb121d extracts read-only operator details (legacy runtime and DTO) into runtime/ui/components/hmi_operator_details.py, service details (legacy runtime and DTO) into runtime/ui/components/hmi_service_details.py, and single-shared MIX observer read into hmi_observer_runtime.py. operator_hmi.py retains reexported function names and sole Telegram publishing handlers; no new action/charge controller, polling, timer, lease or hardware operation. Windows PYTHONUTF8=1 extended 306/306 UI/operator/graph/ownership/recovery tests and 27/27 subtests PASS, compileall and diff --check PASS. node104 D144 slot14 d49cb6d not deployed or restarted. Continue next with remaining pure renderer decomposition and DTO consistency.

## 2026-11-07 - MIX Delta read-only trigger display
Commit 4a98a50 extracts accepted Imin/Vmax and Delta display into runtime/ui/components/hmi_mix_threshold.py, adding precise trigger current (Imin+required Delta) and trigger voltage (Vmax-required Delta). Three decimal places avoid hiding rounding at the current limit. Screenshot EFB80 Imin=1.85A, required Delta ~0.55A and Iset=2.40A: target current lies near Iset, so reaching it in CV may be difficult. No threshold, algorithm, charger setpoint, runtime timer or safety adjustment. Offline Windows PYTHONUTF8=1 source tests: 308/308 PASS plus 27 subtests PASS, compileall PASS, diff check PASS. Production node104 D144 slot14 d49cb6d untouched.

## 2026-11-07 - Live HMI measurements extracted
Commit 7d22859 extracts read-only telemetry projection to runtime/ui/components/hmi_live_measurements.py: output, U/I/power, battery/PSU temperatures, Uset/Iset. Existing V2 sensor precedence and finite parsing preserved. tests/test_hmi_live_measurements.py checks precedence and invalid/missing values. No new safety gate, charge control, timer, hardware operation or polling. Windows PYTHONUTF8=1: 311/311 selected UI/ownership/graph/recovery tests plus 27/27 subtests PASS; compileall and diff --check PASS. Production node104 remains D144 slot14 d49cb6d, no deployment. Next: extract AUTO status presentation without moving charging policy.

## 2026-11-07 - AUTO stage evidence presentation extraction
Commit 6252beb extracts read-only AUTO stage analyzer projection into runtime/ui/components/hmi_auto_stage_progress.py. It reads the same ui_support_snapshot once, preserves existing Imin/Vmax, MIX Delta threshold, MAIN tail readiness, recipe-supplied hold, durable finish-hold and missing/stale evidence behavior. Existing operator_hmi.time.time is passed as now_s callable to retain its clock/test contract; no new timer, stage owner, policy or hardware read path. Focused tests cover CV accepted Delta, single snapshot read, stale progress suppression, analyzer error handling. Windows PYTHONUTF8=1: 314/314 selected UI/ownership/graph/recovery tests and 27/27 subtests PASS; compileall and diff --check PASS. Production node104 D144 slot14 d49cb6d untouched. Next: continue source-only modular extraction, keep charge algorithm and safety unchanged.
