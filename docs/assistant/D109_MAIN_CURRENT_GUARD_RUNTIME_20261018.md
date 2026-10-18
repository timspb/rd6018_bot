# D109 — MAIN Current Guard: действующее снижение тока через единый ExecutionPort

Дата: 2026-10-18. Канонический RD6018 Bot, source-only sprint.

## Результат

Подключён реальный путь уменьшения Iset/OCP при подтверждённой MAIN-сессии EFB/Ca/Ca — через существующий runtime, ExecutionPort и общий task-reentrant owner lock. Никакого нового процесса управления, зарядного рецепта или механизма обновления. Это **реализация в исходниках и испытания на fake-RD**, а не физическая приёмка; работающий node104 пока не изменён.

Фаза MAIN: исходный предел штатного рецепта 0.1C (и существующий лимит 12 А), наблюдение 1800 секунд физически подтверждённого Output ON, затем предложение min(текущий физический лимит, измеренный ток +1 А, начальный предел). Только снижение; после ACK и записи в charge_session.json контроллер обязан использовать новый лимит даже после обычного tick или periodic save.

## Что реализовано

- application/main_guard_checkpoint.py: **две записи в тот же атомарный charge_session.json**: неизменяемое предложение pending до аппарата и финальный confirmed ACK после readback, под существующим lock. Дополнительно сверяются идентификаторы, возраст, химия, целостность старого журнала и исходная уставка. Сохранение не расширяет физическую власть.
- application/main_guard_runtime.py: текущий production runtime вызывает **существующую** транзакцию ExecutionPort только если проверен Native ESPHome lease (armed, не tripped/boot-quarantined, Modbus age <=20 s, remaining >=60 s), Output ON и все исходные Iset/OCP. При HA REST fallback (не прямой ESP Native), HANDS_OFF, отсутствии lease или изменившейся сессии — нет аппаратных команд. Дополнительных lease-renew/arm команд Guard не выдаёт.
- edge_safety_lease.py: необязательный require_native=True, без изменения существующего поведения renew/arm и fallback-наблюдения. Для Guard источник должен быть только Native API ESPHome, а не значения из HA.
- application/main_guard_transaction.py: флаг hardware_write_invoked в результате; при сомнении **после физической команды** запрос OFF и существующий sticky SessionRecoveryGuard.quarantine (останавливает дальнейшие automatic tick/ON). Обычное предварительное отклонение не приводит к ненужному отключению.
- charge_controller.py и runtime/charge/session_atomic.py: после подтверждённого уменьшения обычный расчёт MAIN, восстановленный target и последующие periodic session saves не вправе повысить Iset над сохранённым монотонным пределом. Несогласованный target вызывает GuardJournalError.
- runtime/charge/strategy/main_guard_admission.py: второе и последующие уменьшения теперь проходят с текущим каноническим Guard journal; первая запись больше не блокирует повторный 30-минутный цикл.
- MainGuardShadow: явно признанный новый ungarded canonical epoch может начать независимую сессию после предыдущей АКБ без переноса pending-предложений и старого current ceiling.

## Проверка и важные границы

Прямые интеграционные тесты проходят через ManagedChargeController, настоящий writer charge_session.json, тот же ExecutionPort и FakeOwner с физическими Iset/OCP readbacks. Проверена серия 7→5→3 А, ревизии Guard в журнале 1–5, периодический save без подъёма target, отказ сохранения до физической команды без записи в устройство, сбой ACK после записи с OFF, неприменение HA fallback, отсутствие lease, HANDS_OFF, недавний direct ESP Native, запрет повышенного target.

Автономный ESPHome deadman 900 секунд и AGM не изменялись.

**Следующий практический шаг**: вне зарядного процесса подтвердить Output OFF и готовность стенда, затем штатно развернуть принятую версию после backup и провести испытание на устройстве с напряжением не выше 15.5 В. Отдельно требуется проверка возврата к первоначальному I0 после десульфатации через физический OFF + Iset/OCP readbacks; раньше аппаратной проверки повышение по переходу не разрешаем.

Физического D109 PASS пока нет. Бот на node104 и ESPHome 2.2 этим коммитом не прошивались и не перезапускались.
