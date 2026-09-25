# V3 Legacy Runtime Retirement Plan

## Цель

Перевести production runtime с `bot_legacy.py` на V3 application/runtime
без второго Telegram polling, потери safety-контуров или изменения поведения
заряда.

Главное правило: legacy удаляется последним, после того как все его владельцы
заменены и подтверждены тестами и bench evidence.

## Текущее состояние

```text
bot.py
  |
  +-- V3 application/UI boundaries
  |
  +-- bot_legacy.py
        +-- Telegram Bot/Dispatcher
        +-- controller/FSM/session
        +-- SafetySupervisor/SafeOutputCoordinator
        +-- physical execution
```

V3 уже владеет intent, read models, panel rendering, preflight, plans,
execution boundaries и trace. V2 пока владеет фактическим runtime execution.

## Целевая схема

```text
bot.py
  |
  +-- ApplicationInterface
  +-- TelegramAdapter
  +-- Runtime lifecycle
  +-- Charge runtime
  +-- Safety runtime
  +-- Physical execution owner
```

Должен остаться ровно один `Bot`, один `Dispatcher` и один polling owner.

## Порядок работ

### Phase 0 — Freeze and inventory

- [ ] Зафиксировать baseline и production SHA.
- [ ] Зафиксировать единственный Telegram token и host 101.
- [ ] Составить inventory всех функций `bot_legacy.py`, вызываемых из `bot.py`
      и installers.
- [ ] Составить inventory всех `Bot`, `Dispatcher`, polling и background tasks.
- [ ] Запретить новые прямые UI → legacy runtime зависимости.
- [ ] ACTIVE и physical bench оставить выключенными.

**Gate:** нет неизвестных production entrypoints и второго polling owner.

### Phase 1 — Telegram lifecycle

- [ ] Перенести создание Bot/Dispatcher в отдельный Telegram adapter.
- [ ] Перенести startup/shutdown и command registration.
- [ ] Сохранить один polling path.
- [ ] Проверить `/start`, dashboard, refresh, diagnostics и recovery.
- [ ] Проверить отсутствие duplicate callback registration.

**Gate:** Telegram работает через V3 adapter, но execution semantics прежние.

### Phase 2 — Read and presentation

- [ ] Удалить UI READ-доступ к `bot_legacy` globals.
- [ ] Все snapshots/details/diagnostics/actions получать через
      `ApplicationInterface`.
- [ ] Оставить renderer data-only.
- [ ] Проверить light/dark панели и старые Telegram messages.

**Gate:** presentation не импортирует controller, HA или physical objects.

### Phase 3 — Intent and command routing

- [ ] Завершить маршрутизацию STOP, PAUSE, RESUME и profile selection.
- [ ] Проверить единый route для каждого migrated intent.
- [ ] Оставить legacy handlers только как compatibility wrappers.
- [ ] Удалить прямые Telegram → runtime вызовы после parity tests.

**Gate:** каждый migrated intent имеет одного authoritative owner.

### Phase 4 — Session and ownership

- [ ] Выделить session lifecycle в runtime service.
- [ ] Перенести ownership checks и HANDS_OFF semantics.
- [ ] Доказать restart/re-authorization поведение.
- [ ] Доказать session containment и recovery.
- [ ] Сохранить `ProductionManualSessionManager` как единственного владельца.

**Gate:** нет двух владельцев session state или ownership transitions.

### Phase 5 — Charge controller and FSM

- [ ] Зафиксировать parity V2/V3 для всех charge stages.
- [ ] Перенести orchestration, не переписывая алгоритм без отдельного решения.
- [ ] Перенести transitions, timers, MIX/CV/hold и fault paths.
- [ ] Сохранить единственного владельца FSM.
- [ ] Проверить rollback и process restart.

**Gate:** golden traces и regression matrix совпадают с V2.

### Phase 6 — Safety and physical execution

- [ ] Оставить SafetySupervisor/SafeOutputCoordinator единственным safety owner
      до завершения отдельной миграции.
- [ ] Перенести physical calls только через `PhysicalBridge`/execution port.
- [ ] Проверить verified OFF, OFF_UNCONFIRMED и containment.
- [ ] Провести read-only и DRY_RUN проверки.
- [ ] Провести отдельный разрешённый bench validation.
- [ ] ACTIVE включать только отдельным явным решением.

**Gate:** физическая parity подтверждена evidence; обходов safety нет.

### Phase 7 — Legacy quarantine

- [ ] Убрать `bot_legacy` из production imports.
- [ ] Оставить его только в архиве/rollback branch на согласованный срок.
- [ ] Запретить запуск `python bot_legacy.py` в production.
- [ ] Проверить, что production tree не содержит второго entrypoint.
- [ ] Прогнать full suite и exact-host software validation.

**Gate:** production не зависит от legacy ни по import, ни по execution path.

### Phase 8 — Removal

- [ ] Получить явное approval на удаление legacy.
- [ ] Создать финальный backup/archive вне production tree.
- [ ] Удалить legacy только отдельным commit.
- [ ] Выполнить rollback rehearsal.
- [ ] Подтвердить один entrypoint, один polling, один execution owner.

## Обязательная матрица проверок

- [ ] import graph;
- [ ] namespace/frozen API tests;
- [ ] Telegram route uniqueness;
- [ ] snapshot/details/actions parity;
- [ ] START preflight/parity;
- [ ] STOP/PAUSE/RESUME regression;
- [ ] session ownership/recovery;
- [ ] FSM golden traces;
- [ ] safety deny/containment;
- [ ] physical isolation;
- [ ] DRY_RUN no-mutation;
- [ ] bench evidence;
- [ ] full unittest suite on Python 3.10/3.11/3.12;
- [ ] host 101 service/polling validation.

## Стоп-условия

Работы немедленно останавливаются при любом из условий:

- обнаружен второй polling owner;
- несовпадает V2/V3 decision parity;
- неизвестен владелец session/FSM/safety;
- readback или verified OFF не подтверждены;
- найден прямой UI → physical вызов;
- ACTIVE включается по умолчанию;
- отсутствует rollback;
- production route нельзя однозначно связать с trace.

## Финальные PASS-критерии

```text
one entrypoint
one Bot
one Dispatcher
one polling owner
one ApplicationInterface
one FSM owner
one safety owner
one physical execution owner
no bot_legacy production dependency
```

До выполнения всех PASS-критериев `bot_legacy.py` не удалять.
