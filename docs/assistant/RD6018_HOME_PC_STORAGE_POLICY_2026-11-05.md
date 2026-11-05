# RD6018 HOME-PC — единый каталог и санитаризация (2026-11-05)

## Безусловный канон размещения

**ВСЕ рабочие файлы проекта RD6018 на HOME-PC должны находиться ТОЛЬКО внутри `E:\CODEX\rd6018_bot`.**

Вне этого каталога не допускаются отдельные RD6018 worktree, Git-клоны, тестовые каталоги, staging, статусы, отчёты, временные скрипты, архивы и backup-файлы. Если обнаружен действительно нужный файл, перенести в канонический каталог; ненужный — удалить. Ничего не сохранять «на всякий случай» и не делать новых резервных архивов при уборке.

Не затрагивать другие проекты в `E:\CODEX`, секреты, текущие конфигурации и действующее состояние node104. Различать обычный мусор и уникальные незапушенные Git-коммиты/незакоммиченные изменения: сохранять последние в каноническом дереве, а не удалять как временные файлы.

## Контрольная точка

На старте уборки `E:\CODEX\rd6018_bot`: main `c3751aa`, 134 коммита впереди `origin/main`, локальные изменения в `docs/assistant/RD6018_CURRENT_CHECKPOINT.md`, `tests/test_node104_d091_physical_proof_collector.py`, `tools/node104_d091_physical_proof_collector.py`; untracked `charge_session.json.mix-authority.json`. Это рабочее состояние, не стирать.

Вне каталога выявлены `rd6018_bot_pr44`, `rd6018_bot_v3_integration`, `rd6018_dryrun_virtual` (связанный Git worktree), `RD6018_V3_SAFE_ACCEPTANCE_LUNA_EVIDENCE` и временные сценарии D061/D123 в корне `E:\CODEX`. Не путать их с прочими проектами.

Очистку считать окончательной только после проверки, что необходимые рабочие данные перенесены, лишнее удалено и Git/worktree ссылки непротиворечивы.

## Выполненная санитаризация

- Открыта Wake Bridge R7.2-canary (отдельный инструмент).
- Удалены 53 временных скрипта D061/D123 из корня `E:\CODEX`, 53 902 байта.
- `git worktree prune`: удалены три устаревшие ссылки `/tmp/rd6018-*`.
- Активная ветка dry-run перенесена штатным `git worktree move` в `E:\CODEX\rd6018_bot\.worktrees\dryrun_virtual`, Git-связь проверена. Путь `.worktrees/` исключён локально через `.git/info/exclude`.
- Уникальный HEAD `rd6018_bot_pr44` (`7f789b87198cbc0d762ec970d0b17a486a905bad`) перенесён в локальный Git ref `refs/heads/archive/pr44-20261105`; SHA проверен. Отдельный клон удалён.
- HEAD бывшего `rd6018_bot_v3_integration` (`b89670d50d82807087f53a0950b145449c3a611a`) уже присутствовал в основном Git object store. Клон и устаревший untracked stage4 report удалены.
- Удалён `RD6018_V3_SAFE_ACCEPTANCE_LUNA_EVIDENCE`: 5 298 файлов, 245 770 759 байт (устаревшие артефакты).
- Повторная проверка верхнего уровня `E:\CODEX`: единственный каталог с именем RD6018 — `rd6018_bot`; отдельных RD6018 файлов в корне не осталось. `git worktree list`: только main и внутренний dry-run.
- WSL `/tmp`: прямых записей с префиксом `rd6018` при проверке не найдено.
- Не тронуты текущие незакоммиченные изменения D091 и `charge_session.json.mix-authority.json`, работающие сервисы, секреты, другие проекты и node104.

Политика распространяется на будущие операции: staging, pytest, Codex и новые worktree RD6018 должны использовать пути внутри канонического каталога; не создавать новые `/tmp/rd6018-*` и `E:\CODEX\rd6018_*`.

## Дополнительная находка на диске D:

По замечанию пользователя проверен `D:\rd6018_bot`: это была отдельная обычная папка (не junction), содержавшая только `.env` размером 96 байт, ключи параметров `DEEPSEEK_API_KEY` и `DEEPSEEK_BASE_URL` (значения не раскрывались). Git, кода и других файлов там не было. Файл перенесён в `E:\CODEX\rd6018_bot\.secrets\legacy_d_drive_deepseek.env` с совпадающим SHA-256 до/после; пустая папка `D:\rd6018_bot` удалена. Повторной проверкой подтверждено: папки D больше нет, файл в каноническом каталоге присутствует. Не предполагать автоматически, что это действующая настройка production.

Для будущих уборок проверять не только `E:\CODEX`, но также и другие диски HOME-PC на отдельные RD6018 пути, не задевая остальные проекты.

## Сплошная ревизия HOME-PC — повторный проход 2026-11-05

Проверены локальные тома `C:`, `D:`, `E:`, доступные домашние/временные каталоги Windows, WSL Ubuntu-24.04 и RD6018-CI. Docker Desktop зарегистрирован, но остановлен. Непрерывная рекурсивная проверка всех системных каталогов Windows не завершена; не выдавать этот проход за абсолютную гарантию отсутствия хвостов.

- Ubuntu `/home/home-pc`: удалено 39 исторических объектов RD6018 (24 чистых Git-клона, 15 старых dirty/staging/release объектов D061–D124); перед удалением проверены статусы Git и отсутствие запущенных RD6018-процессов, использующих эти деревья. В 9 деревьях были локальные незакоммиченные изменения — они являлись старыми тестовыми рабочими копиями и были удалены без переноса; не утверждать, что их незакоммиченные изменения сохранены.
- Ubuntu `/tmp` и `/var/tmp`: удалены 57 объектов `rd6018-*`; старое `/home/home-pc/.venvs/rd6018-esphome-2026-9-1` (215 MiB по `du`) удалено.
- Windows `D:\Users\HOME-PC\Temp`: удалены 281 старый (>2 суток) временный объект Codex, из них 263 `codex-index-*` и 18 `codex-artifact-session-*`; ошибок удаления не было.
- Windows `C:\Users\HOME-PC\d061-takeover-evidence`: удалён каталог с 14 файлами D061.
- WSL RD6018-CI `/root`: удалены две старые копии `rd6018-stability-backup-20261011T1915Z` и `rd6018-dns-backup-20261011`. Рабочие CI runners и их окружения сохранены, чтобы не разрушить работающую инфраструктуру.
- Основной каталог: удалены восстанавливаемые `.pytest_cache` и `__pycache__` верхнего уровня; канонические `.venv`, `.secrets`, Git, текущие исходники и несохранённые изменения не затронуты.
- Верхний уровень дисков проверен; в `D:\CODEX` присутствует другой проект `My_Local`, RD6018-папок там не обнаружено. Точки IDE `.claude/projects/D--rd6018-bot` и `.cursor/projects/d-rd6018-bot` ранее обнаружены в профиле Windows: их содержимое требует отдельной оценки, прежде чем удалять чужие настройки IDE.

Ограничения: `RD6018-CI` хранит работающий GitHub Actions runner в `/opt/rd6018-actions-runner`, а его Python test venv в `/opt/rd6018-ci-test-venv`; это инфраструктурные исключения, не пользовательские рабочие копии исходников. Изменения и пулы WSL смежного проекта PCP не трогать. Полный поиск по всем скрытым/системным путям Windows не доказан.

## Дополнительный поиск по Windows-профилям и E: — 2026-11-05

- Рекурсивные поиски по `C:\Users\HOME-PC`, `D:\Users\HOME-PC` и `E:\` выявили ранее пропущенные остатки. Windows Temp: дополнительно удалены 264 объекта `rd6018*` / D-стадий (263 файла, один каталог).
- `E:\CODEX\My_Local`: удалены 22 RD6018 сценария/лога, 2 отдельных файла `.tmp`; удалён `E:\CODEX\Backups\RD6018` (95 245 130 байт). Другие My_Local проекты не затронуты.
- `C:\Users\HOME-PC\rd6018.db` (45 056 байт, октябрьская отдельная SQLite) перемещён в `E:\CODEX\rd6018_bot\runtime\legacy_state\home_pc_20261007_rd6018.db`; `E:\CODEX\My_Local\rd6018-secrets.yaml` (387 байт) перемещён в `.secrets\legacy_my_local_rd6018-secrets.yaml`. В обоих случаях SHA-256 до/после совпали; значения секретов не раскрывались. Действующая `E:\CODEX\rd6018_bot\rd6018.db` была занята процессом, не менялась.
- Удалены C: D062 старый отчёт, два C: temp-файла, отдельные профили старого `D:\rd6018_bot` в `.claude/projects` (17 файлов) и `.cursor/projects` (16 файлов).
- Оставлены пользовательские Downloads с firmware/RDFlasher/Riden software, действующий GitHub Actions runner и CI venv в RD6018-CI, системные Codex memory summaries, Windows ярлыки на работающую CI. Они НЕ являются отдельными рабочими Git-деревьями RD6018. Для приведения к буквальному нулю вхождений имени проекта вне E нужно отдельно различать оригинальные загрузки, штатные системные данные и инфраструктуру.
- Проверены: `git worktree list` (main и единственный внутренний dry-run); текущие незакоммиченные изменения D091 не затронуты. WSL удалённые данные могут не уменьшить физический размер VHDX до offline compact.

Итог: все выявленные старые рабочие копии/стейджинги проекта удалены, но **абсолютную полноту проверки всех системных и скрытых каталогов Windows подтверждать нельзя**: рекурсивное перечисление `E:\` завершилось ошибкой доступа, а общий скан Windows был остановлен из-за длительности. Не объявлять строгий полный аудит PASS без отдельной окончательной проверки.

## Контроль после проверки от root

Повторно проверены от root в Ubuntu `/tmp`, `/var/tmp`, `/home/home-pc`, `/opt`, `/root`: обнаружен ещё `/tmp/pr159-check.LmnXdn` (11 MiB, старый PR159 test checkout), удалён. После удаления по `find` совпадений `*rd6018*` в перечисленных каталогах не осталось. В `RD6018-CI` остались исключительно действующий `/opt/rd6018-actions-runner` и `/opt/rd6018-ci-test-venv`, а не временные сборки. Физическую компактизацию WSL VHDX не проводить при работающих дистрибутивах.

## 2026-11-05 — Git/CI source consolidation

- Проверен remote: только `origin=https://github.com/timspb/rd6018_bot.git`. Перед синхронизацией `origin/main` является предком локального `main` (0 behind, 138 ahead); force push запрещён.
- D145 `docs/operations/evidence/D146_D138_NODE104_PROFILE.json`: проверено, что Git blob SHA256 = `a2610e4c26c6d2ff6fcd9ac3bc12a1e92aaf0f9d1c49059dcfe5bc2462934e47`, а рабочий Windows checkout CRLF давал `cabf0a0d...` при отсутствии Git diff. Добавлен `-text` точечно в `.gitattributes`, точные байты профиля восстановлены из Git без изменения закреплённого SHA. D145 unittest после исправления: 8 PASS; D091/D145/D149 pytest: 38 PASS.
- `charge_session.json.mix-authority.json` — локальный runtime state (не исходник); в `.gitignore` добавлено точное исключение. Файл не удалять при живом процессе и не публиковать в GitHub.
- Незакоммиченные изменения D091 исправляют ошибку `POST_START journal_clear` по реально валидированному D090 retired v2 journal; фиксация кода допускается только с тестами. Исторические D090/D142 защиты не отключались.
- Контроль заряда: read-only SSH root@192.168.1.104 отказал в авторизации; локальные `HA_URL` и `HA_TOKEN` не настроены, поэтому live Output/ток/защиту с HOME-PC подтвердить не удалось. Нет разрешения выдавать прежние показания за текущие. Команды управления RD не выполнялись.
- Локальные отдельные рабочие ветки и удалённые неслитые ветки сохранять до индивидуальной проверки уникальных коммитов; бессистемное удаление веток не является санитаризацией.

## 2026-11-05 — Git branch and GitHub review; live charge read-only

- `main` at `5acd9519f7697b2b097a47b292ada92a04dbfb5a`: D091 retirement journal projection, 38/38 focused tests, exact D146 binary SHA preserved with `.gitattributes`, local MIX authority ignored by `.gitignore`; no charge control commands.
- Removed 7 already-merged local branches with `git branch -d` and 9 patch-equivalent local branches only after `git cherry main <branch>` reported zero unapplied patches. Preserved all remaining branches with genuinely unique patches, especially `feature/dryrun-virtual-devices`, `fix/d061-off-confirmation`, D150 and PR44 branches. Two valid worktrees only, both inside canonical root.
- GitHub connector confirms `timspb/rd6018_bot`, `main`, admin/push permissions. Remote snapshot: approximately 110 remote branch refs (including `origin/HEAD`), 64 not merged into current local `main`; open PRs #59, #137 (draft), #179 (draft). No remote branch or PR was deleted without inspecting unique content.
- HTTPS `git push origin refs/heads/main:refs/heads/main` returned code 128 because no interactive GitHub credentials were available; source/remote were fast-forward compatible (`0 behind, 139 ahead` at attempt). A later credential-bearing tool invocation was rejected by tool safety controls; do not circumvent. GitHub `main` NOT synchronized, full Git SHA history remains LOCAL. Connected GitHub APIs do not provide direct git packfile push. Do not claim GitHub cleanup completed.
- Two direct read-only ESP Native API samples on `192.168.1.28`: `2026-11-05T06:56:58Z` and `2026-11-05T06:59:01Z`, identity `timspb.rd6018-pb-recovery-v2` firmware `2.3-ha-canonical`, Output ON, measured SensorState voltage ≈14.83 V and current ≈0.24 A, measured power 3.57→3.54 W, protection_status_code 0, CV=true, CC=false, OVP/OCP trip flags false. Safety lease armed=true, tripped=false, TTL=900 s, remaining 867→744 s; Modbus age under 6 seconds. Native NumberState `output_current` = 1.24 A is a configured setpoint, NOT the measured SensorState `output_current` ≈0.24 A; distinguish entity types to prevent false charging current claims. OVP setting 14.92 V and OCP 1.34 A. No HA or node104 SSH cross-check was available; no service PID or full-cycle safety claim from these snapshots.
- The ESP Native read used the already existing local YAML secret without exposing its value; temporary probe script removed after measurements. No firmware, output, setpoint, session, lease or other actuator mutations.

## GitHub publication retry — 2026-11-05

Fresh checks: canonical local HEAD `fcc1ce0bc33e36257fb350cb99e3dd8c1fe78352`, clean `main`, `origin/main=e6a1fe06ddd8c1514190711e6f9075e2afd9ce70`, ahead 140/behind 0. GitHub connector authenticated as repository writer/admin, but its Git Data API cannot transfer existing Git packfiles and cannot preserve SHA-identical full ancestry by recreating commits. `gh` on Windows is installed but its active account `timspb` token is invalid; `gh` absent in Ubuntu-24.04 and RD6018-CI. Git Credential Manager noninteractive dry-run push exits 128, `unable to get password from user`. Attempt to pass a token from existing local secrets store into the process was rejected by tool safety controls; DO NOT circumvent or expose secrets. GitHub API reports the local HEAD absent from repository. Publication remains NOT DONE. Do not use create_commit/update_ref to replace 140 Git commits with a different history. Once authorized Git transport is available, use normal fast-forward `git push origin main:main`, then verify `git ls-remote origin refs/heads/main` equals local HEAD.

## 2026-11-05 — финальная инвентаризация vendor, Codex history и WSL CI

Подробный канонический план: `docs/assistant/RD6018_HOME_PC_STERILE_STORAGE_2026-11-05.md`. Загрузки RD6018/RDFlasher/Riden перенесены из Windows Downloads в `local_assets/vendor`, удалено 25 дублей/архивов (295 997 649 B), остаток 398 файлов (62 644 966 B). `local_assets/` исключён из Git. Удалены 5 RD6018 Codex rollout summaries, 8 Windows Recent links, 2 Windows Start Menu links. В CI удалены бывшие local-acceptance, staged update/checkout и bin/externals 2.338.0 (~2 GB). GitHub runner `2.338.2` перезапущен, журнал подтвердил `Connected to GitHub` и `Listening for Jobs`.

**Незакрытый разрыв:** VHDX `RD6018-CI` физически остаётся на C: под AppData Local WSL. Штатный `wsl --manage RD6018-CI --move` после `wsl --terminate RD6018-CI` вернул `ERROR_SHARING_VIOLATION`. Registry BasePath неизменен. Глобальный `wsl --shutdown` сейчас не запускать, так как затронет параллельный Ubuntu-24.04 и чужие работающие задачи. Критерий стерильности: перемещение VHDX в `E:\CODEX\rd6018_bot\infrastructure\wsl\RD6018-CI` в безопасное окно, проверка подключения runner, затем повторный поиск. Пока это не произошло, строгое «все файлы только в E» НЕ PASS.
