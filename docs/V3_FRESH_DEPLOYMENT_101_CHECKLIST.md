# V3 Fresh Deployment Checklist — node 101

Статус документа: только подготовка. Этот документ не выполняет deployment,
не создаёт каталогов на node 101 и не запускает systemd.

Целевой revision:

```text
eea855a366e016bdb28e5e0fe042cbe80c3c5e54
feat(v3): wire production start through dry-run boundary
```

## Safety boundary

До отдельного разрешения запрещены:

- ACTIVE START;
- physical execution;
- RD writes;
- enable Output;
- set voltage/current/OVP/OCP;
- восстановление старого дерева или старого runtime state.

Первый запуск должен быть non-actuating. START остаётся `DRY_RUN`, а V3 не
становится владельцем V2 controller/FSM/physical execution.

## 1. Target tree

После отдельного разрешения deployment:

```text
/root/rd6018_bot
```

Проверить до загрузки:

- каталог отсутствует или пуст;
- нет старых backup/staging/rollback-копий;
- нет старого `.git` state, если deployment выполняется архивом;
- секреты не входят в Git bundle/archive.

Не восстанавливать автоматически:

- `rd6018.db`;
- session JSON;
- `rd_control_mode_v2.json`;
- старые runtime snapshots.

## 2. Host/runtime preflight

На node 101 перед установкой зафиксировать:

```bash
hostname
cat /etc/os-release
id
python3 --version
command -v python3
```

Требования:

- поддерживаемая ОС и архитектура;
- Python 3.11+;
- отдельный validated venv;
- доступ к DNS/HA/Telegram только после read-only preflight;
- service user и права на каталог определены явно;
- права секретного файла не шире `600`.

После cleanup старый `/opt/rd6018-bot-venv` отсутствует, поэтому новый venv
нужно создать и проверить отдельно. Нельзя использовать системный Python,
если он не соответствует поддерживаемой версии.

## 3. Source and dependency validation

На чистом checkout/archive проверить:

```bash
git rev-parse HEAD
python -m pip install -r requirements.txt
python -m compileall -q .
python -m unittest discover -s tests -p 'test_*.py'
```

Acceptance:

- `git rev-parse HEAD` равен `eea855a366e016bdb28e5e0fe042cbe80c3c5e54`;
- compileall PASS;
- полный unittest PASS;
- тесты не изменяются на node 101;
- при любом FAIL сервис не создаётся/не запускается.

## 4. Environment and secrets

Использовать только сохранённый secret source, без старого runtime state.

Целевой файл на node:

```text
/root/rd6018_bot/.env
```

Требования:

- секреты передаются отдельно от source tree;
- `.env` имеет права `600`;
- значения не попадают в journal, Git, отчёты или командную строку;
- проверяются обязательные HA/Telegram/AI переменные;
- старые backup `.env` не восстанавливаются;
- отсутствие обязательного секрета даёт fail-closed preflight.

Не добавлять rollback-флаги в обычную конфигурацию:

```text
V2_UI
V2_AUTHORITATIVE
```

`RD6018_EDGE_LEASE_REQUIRED` не отключать. Значение по умолчанию должно
оставаться fail-closed.

## 5. Proposed systemd unit

Unit создаётся только во время отдельного deployment, не на этапе подготовки:

```ini
[Unit]
Description=RD6018 Telegram Bot V3 dry-run boundary
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/root/rd6018_bot
EnvironmentFile=/root/rd6018_bot/.env
ExecStart=/opt/rd6018-bot-venv/bin/python /root/rd6018_bot/bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Перед применением unit отдельно подтвердить service user. Нельзя молча
наследовать `root`, если все необходимые права можно выдать dedicated user.
Нельзя запускать unit до завершения non-actuating validation.

## 6. First boot validation

После отдельного разрешения запуска, строго по порядку:

### Import boundary

- `bot.py` импортируется без traceback;
- production import graph не активирует V3 physical executor;
- `PhysicalExecutionGate` остаётся неактивным;
- нет ACTIVE wiring;
- нет прямого UI → physical вызова.

### Runtime startup

- service active и стабилен;
- один PID;
- нет restore старого session/state;
- нет неожиданных HA writes;
- нет Output enable;
- journal не содержит import/config/auth loop.

### Telegram/UI

- polling устанавливается;
- `/start` возвращает графику и панель;
- dashboard обновляет существующее сообщение;
- diagnostics открывается через Application Interface;
- START route доходит до V3 preflight/DRY_RUN;
- реальный `start_profile_transactional()` не выполняется;
- ACTIVE отклоняется gate.

### Read-only physical checks

Разрешены только чтения:

- HA entity discovery;
- telemetry/readback;
- lease entity visibility;
- output state observation.

Запрещены:

- ENABLE;
- DISABLE как deployment smoke test;
- setpoints;
- reset protection;
- charge start.

## 7. Blockers before actual deployment

До deployment должны быть закрыты:

- подтверждён exact target SHA;
- validated Python 3.11+ environment;
- dependency installation and full tests PASS;
- secure `.env` transfer verified by hash, without printing values;
- edge failsafe/lease contract compiled and bench-validated for exact target;
- service user and permissions approved;
- systemd unit reviewed;
- no old runtime state selected for restore;
- ACTIVE disabled by configuration and policy;
- deployment rollback package prepared separately from old Frankenstein trees.

## 8. Rollback boundary

Rollback до первого production execution должен означать только:

- остановить новый service;
- сохранить logs/evidence;
- удалить/отключить новый unit;
- не восстанавливать старый bot автоматически;
- не включать физический Output;
- вернуть систему в безопасное состояние отдельной согласованной процедурой.

## Current preparation result

```yaml
target_sha: eea855a366e016bdb28e5e0fe042cbe80c3c5e54
deployment_executed: false
service_created: false
service_started: false
active_execution: false
physical_execution: false
old_runtime_restored: false
```
