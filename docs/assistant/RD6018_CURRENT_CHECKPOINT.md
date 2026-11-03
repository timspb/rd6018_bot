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
