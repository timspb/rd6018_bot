# RD6018 node104 — reconciled deployment plan (2026-11-04)

This is a read-only preparation plan, **not permission to activate or interrupt a charge**.

## Evidence and installed architecture

Source commit: 91c72df25b60a9435ad066385b9a4e5e39ecdedb. Full 59-file source
comparison with verified remote SHA256 is in RD6018_NODE104_DEPLOY_DELTA_2026-11-04.json.
13 source files match byte for byte, 40 differ, and 6 are absent on node104.

The systemd service executes /opt/services/rd6018-bot/venv/bin/python
/opt/services/rd6018-bot/app/bot.py as user rd6018. Working directory is
/opt/services/rd6018-bot/state. Code is root-owned; state is writable by
rd6018. The persistent DB rd6018.db, user_recipes directory, recovery
quarantine, and MIX-authority file are present. No active charge_session.json
was found at the checked app/state paths, but external charging under
hands_off is still possible. Systemd service active PID 196930, no restarts;
persisted control mode hands_off. Last read-only clock 2026-11-03 14:22 UTC.

The local migration affects bot initialization, operator and Telegram UI,
database interfaces, controller targets, MAIN/MIX/DESULFATION/SAFE_WAIT owners,
session restore, and recipe versions. Do **not** install only six missing files
or just the Telegram UI. This inventory is the difference from Git origin/main,
NOT a complete dependency-closed release manifest.

## Candidate preparation

1. Re-read the existing node104 deployment/release scripts. Build the candidate
   from the **complete exact tested Git source**, not from incremental patches.
   Include a normalized full-file SHA256 manifest and dependency/import checks.
2. Run the complete regression suite on the exact candidate in an isolated
   checkout. Earlier c637922 source baseline passed 2849 tests, 1666 subtests
   with 3 skipped; later commits 3cd4ead and 91c72df changed documentation.
3. Check Telegram catalog, button callbacks, graphs, hands_off display, recipe
   state persistence, and restart restore with fake hardware, no external
   polling token and no second charging owner.
4. Exclude and preserve outside the candidate: .env, secrets, venv,
   /opt/services/rd6018-bot/state, logs, backups, rd6018.db, user_recipes,
   control mode and all operational state. Respect existing systemd unit.
5. Compare expected live file hashes and service state again immediately
   before activation; re-evaluate drift rather than force overwrite.
6. Store one coherent recoverable prior source release and its manifest.
   Avoid recursive backups and uncontrolled cyclical rollback.
7. Activate only when physical charge/ownership is understood and service
   interruption is safe. Restarting the Telegram service is NOT safe to assume
   during a live externally controlled charge.
8. Verify exactly one polling owner, hands_off unchanged, DB and graphs intact,
   versioned native copies and original recipes usable. No physical START/OFF
   or setpoint action without explicit operational control transfer.

## Disposition

Candidate not installed. node104 not modified, service not restarted,
physical charging not touched. A local untracked
charge_session.json.mix-authority.json is test-produced, not part of release;
do not delete it while an old test owns it. Do not push into foreign upstreams.

Next: locate and validate the existing release installer, generate a complete
source manifest, and test in isolation before a controlled deployment window.

## Offline candidate trial

The existing tools/node104_atomic_deploy.py stage command produced a verified
local candidate from exact HEAD 82659d5, under
/tmp/rd6018-release-candidate-20261104 on HOME-PC WSL only (not on node104).
Its complete source.tar is about 9 MB, with a 251 KB release manifest.
The stage constructor checked archive digest and all unpacked source hashes.

Full pytest inside the source-only archive gave 2842 passed, 9 skipped,
1 failed, 1658 subtests passed. The lone failure was an old D123 test
calling git rev-parse from inside an archive that intentionally lacks .git.
The D123 VCS-only fixture has now been correctly scoped with skipUnless to
a Git checkout, while still running in CI/source worktrees. The five
other D123 source-release tests pass in the Git worktree (5 passed).
This is a test-environment contract adjustment, not a bypass of charger
behavior. Re-stage and re-test from the next committed source HEAD.

Do not infer a production deployment from this offline candidate.

## Verified release candidate fa60c16

The second candidate was staged by the existing offline
tools/node104_atomic_deploy.py from exact commit fa60c16 under
/tmp/rd6018-release-candidate-20261104/release-fa60c16cc4bf3420d29bf0cfad184d9572e6182f-iv_je3jp.
The staging operation verified the source.tar digest and its complete
unpacked file SHA256 manifest.

Entire pytest suite inside the unpacked **source-only** candidate:
**2842 PASS, 10 SKIPPED, 5 WARNINGS, 1658 subtests PASS, 0 failures and
0 errors** in 138.71 seconds. Evidence:
HOME-PC WSL /tmp/rd6018-candidate-fa60c16-full.log.
VCS-dependent tests properly skip in source-only releases; D123 tests pass
in the local source checkout.

The successful offline candidate is not a deployed or activated release.
No remote service restart, database write, hardware output, or state
migration took place. The node104 live baseline must be rechecked before
any installation or switch-over.

## 2026-11-04 — Install mechanism review (local source inspection)

Inspected `tools/node104_atomic_deploy.py` directly. Its module header explicitly says **no production activation, SSH, systemctl, OTA, lease, or actuator operation is implemented**. Supported CLI phases are `manifest`, `preflight`, `stage`, `recover`, and `simulate`; the swap and rollback paths operate only inside a marked simulation root. `stage()` is an appropriate offline packager, **not** a live installer.

The script also retains historical firmware assertions (`2.0-edge-adoption` to `2.2-autonomous-authority`) whereas node104 previously reported ESPHome `2.3-ha-canonical`. Do not use its `preflight` as current device authorization and do not add artificial evidence/signatures to satisfy the old contract. The D090 script is similarly offline and pinned to an obsolete source/firmware revision.

**Corrected deployment boundary:** the fa60c16 source archive is verified offline; there is no identified live deployment executor suitable for this release. The next task is to inspect the actual existing node104 release transaction/handoff (not invent another launcher), validate exact app+state segregation and service lifecycle, and only then arrange a coherent installation without interruption of active external charging. The historical SHA delta is informational and must be refreshed against the production host immediately before activation.

The execution shell connector declined commands in this turn, so no new remote baseline, simulation execution, or Git commit was obtained. This review was performed through direct read-only source inspection. No production writes or hardware actions occurred.

## 2026-11-04 — действующий исполнитель обнаружен (read-only)

На HOME-PC найден реальный производственный владелец `RD6018_V3_SAFE_ACCEPTANCE_LUNA_EVIDENCE/node104_d090_transaction_live.py`. У него есть `prepare/activate/recover` и `--python-release-profile`, поддержанный `tools/node104_d124_release_profile.py`; вспомогательный D145 binding работает внутри того же владельца и блокировки, а не запускает второго бота. `tools/node104_atomic_deploy.py` по-прежнему является только локальным упаковщиком и симулятором.

Read-only на node104 (удалённые часы 2026-11-03 14:45 UTC): `rd6018-bot.service` active, PID 196930, NRestarts=0; control mode `hands_off`. Файлы `/opt/services/rd6018-bot/d090/node104_d090_transaction.py` и `/opt/services/rd6018-bot/app/tools/node104_d124_release_profile.py` присутствуют. Корневой D090-журнал существует, фаза `STARTED`, `source_sha=930239c670899e14ccb09154d99baf77df90da10`, **`candidate_inventory` отсутствует**. Маркер `.deploy_sha=58321a866dd68195bf8264d1d9ebe7c18a60748f` не соответствует исходному SHA журнала. Не трактовать исторический D090 как завершённый COMMITTED и не переписывать журнал ради нового обновления.

Текущий готовый релиз `fa60c16` прошёл 2842 теста в исходном архиве, но **не привязан к производственному D090/D145 профилю**, текущему installed-app inventory и реальному процессу на node104. Для обновления требуется использовать существующий D090/D145 owner с точно собранным Python-release profile, сопоставить предварительный снимок production app/venv и корректно завершить/обойти историческую незавершённую транзакцию средствами самого владельца. Никаких новых криптографических подписей, параллельных оркестраторов или искусственных допусков не вводить. Проверка состояния зарядки перед перезапуском остаётся обязательной как реальный риск, а не формальная авторизация.

**Изменения на node104 отсутствуют**, сервис и аппаратный выход не тронуты. Следующий исполняемый шаг: сравнить конкретные требования `D090Transaction.prepare/activate` и D145 binding с текущим журналом и точным релизным профилем, составить адресный план восстановления связности без нового исполнителя. После этого проверить read-only фактическое управление АКБ и возможность безостановочного переключения (если не подтверждается, оставлять production без изменений).

## Дополнение 2026-11-04 — наличие D145 на самом node104

Повторный read-only `find` по `/opt/services/rd6018-bot` (maxdepth 5) **не обнаружил файлов D144/D145**. В установленном `/opt/services/rd6018-bot/d090/node104_d090_transaction.py` есть `--python-release-profile`, но `_layout` по-прежнему отклоняет существующий D090-журнал (`existing/incomplete D090 journal requires recovery`). Локальный `d145_owner_binding_v2.py` из HOME-PC нельзя считать установленным производственным компонентом. Следующее действие — сопоставить локальный D145 с текущим D090 owner и провести офлайн-тест их совместимости на точной копии состояния `STARTED`, затем подготовить единый релиз/обновление существующего владельца. Ничего на node104 не записано.

## 2026-11-04 — D145 entrypoint test and byte-parity diagnosis

В локальном checkout `tests/test_node104_d145_entrypoint.py` + D144 owner/transition: **25 PASS, 3 FAIL**. Все 3 отказа — один и тот же D146 profile SHA: в Windows рабочем дереве `docs/operations/evidence/D146_D138_NODE104_PROFILE.json` переведён в CRLF (`git ls-files --eol`: `i/lf w/crlf`), SHA рабочих байтов `cabf0a0d…`, ожидаемый по Git blob `a2610e4c…`. В релизном архиве `fa60c16` файл имеет строго правильные Git-байты и **8/8 D145 entrypoint PASS**. Не переписывать исходный профиль и закреплённый SHA для обхода Windows-перевода строк; использовать clean Git archive/candidate.

Существующий D145 entrypoint в исходниках строго привязан к **старому** D146 source SHA `d351c208…`, preimage digest `9651e979…` и candidate identity `45b6ae0e…`; он не является универсальным launcher для `fa60c16`. Установленный node104 D090 журнал остаётся `STARTED` с source `930239c6…`, `.deploy_sha=58321a86…`; D145 на сервере отсутствует. Следовательно, нельзя запускать старый entrypoint на новом релизе или менять его SHA без сверки exact live preimage и контрактов D090/D145.

Исполнительный путь: использовать действующие `D090Transaction` и `D144 OwnerTransition` в офлайн-моделировании фазы `STARTED`, сверить реальный current app/venv inventory и D146 software release profile, затем готовить **один** согласованный релиз и путь установки через прежнего владельца. Пока node104 только read-only, зарядка и сервис не затрагивались. Полный релизный pytest `fa60c16`: 2842 PASS, 10 skipped; новая диагностика D145 не отменяет этот результат.

## 2026-11-04 — exact offline candidate 095e545 and physical status

Staged a **new exact-head source release** via existing `tools/node104_atomic_deploy.py stage` (no node104 writes): source SHA `095e545dcd092c84776f6196296f69848aff40e5`, offline candidate `/tmp/rd6018-release-candidate-20261104/release-095e545dcd092c84776f6196296f69848aff40e5-h78vpxwf`. Focused D137/D142/D144/D145 tests in extracted candidate **35 PASS, 7 subtests PASS**. Full extracted-candidate pytest **2848 PASS, 10 skipped, 5 warnings, 1658 subtests PASS, 0 failures/errors** in 141.58 s. Log `/tmp/rd6018-candidate-095e545-full.log`. Source-only archive intentionally skips VCS-only tests; this does not authorize physical activation.

Read-only HA REST (`2026-11-03 15:12–15:13 UTC`, remote clock) confirmed **Output ON** by fresh `sensor.rd6018_rd_6018_output_state_code_v2=1`, `sensor.rd_6018_output_voltage≈14.67 V`, `sensor.rd_6018_output_current≈0.05 A`, `sensor.rd6018_rd_6018_output_power_v2≈0.82 W`, battery voltage ≈14.66 V; Modbus age ≈2.48 s, protection code 0. `hands_off` and lease remaining 0 (lease sensor itself last updated 2026-11-02). The HA switch entity's last update was older, so fresh Output-state and measured electrical values are primary. **No active bot-owned `charge_session.json` does NOT mean OFF.** The existing OFF-only D142/D090 release condition must reject current output state; extra tests for ON and divergent HA/ESP claims were added without introducing a new guard.

**Deployment HOLD because physical Output is ON**; no service restart, physical START/OFF/setpoint change, takeover, or journal modification. On HOME-PC older pytest processes remain running despite completed historical logs; the untracked root `charge_session.json.mix-authority.json` is 145 bytes and may be re-created by their tests. Leave it out of Git/deploy and do not kill processes/erase their artifact without attributing ownership. New clean candidate is available for a later safe maintenance window; hardware status must be re-observed then. Next: reconcile historical D090 `STARTED` and current D137 retired-session assumption through existing owner only, when genuine physical state permits; do not fake retirement or install D145 while Output ON.
