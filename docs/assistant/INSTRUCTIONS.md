# Инструкции для ассистента в этом репозитории

## С чего начинать

Перед любой работой прочитать в таком порядке:

1. `AGENTS.md` — operational/safety rules для агентов;
2. `README.md` — текущая production-архитектура;
3. `docs/DEPLOYMENT.md` — если задача про узел, обновление, systemd или rollback;
4. `docs/assistant/CHARGE_STRATEGY.md` — если задача касается стратегии заряда;
5. `docs/assistant/PB_RECOVERY_V2.md` — если задача касается V2 architecture/invariants.

Не восстанавливать production semantics по старым коммитам или legacy-комментариям, если они расходятся с этими документами и текущими тестами.

## Репозиторий и ветки

Не предполагать, что работа всегда идёт напрямую в `main`.

Перед изменениями:

```bash
git status --short --branch
git rev-parse HEAD
git branch --show-current
```

Если пользователь указал branch/SHA — работать строго там. Не мержить PR и не менять `main` без отдельного запроса.

## Production entrypoint

Штатный V2 запуск:

```bash
python bot.py
```

- `bot.py` — маленький production entrypoint;
- `bot_legacy.py` — сохранённый предыдущий runtime;
- `ProductionChargeControllerV2` — штатный live controller.

Rollback-флаги:

```text
V2_UI=0
V2_AUTHORITATIVE=0
```

Не выставлять их при обычном V2 deployment без явного запроса.

## Deployment

Не предполагать путь `/root/rd6018_bot`, имя systemd unit или virtualenv. Сначала обнаружить фактическое состояние узла.

При deployment-задаче не менять код, thresholds, recipes, UI или schema. Следовать `docs/DEPLOYMENT.md`.

Никогда не перезаписывать без явного запроса:

- `.env`;
- Telegram/HA credentials;
- service environment overrides;
- SQLite/history;
- session/runtime JSON;
- локальные operator settings.

## После изменений кода

Минимальная обязательная проверка:

```bash
python -m compileall -q .
python -m unittest discover -s tests -p 'test_*.py'
```

Не удалять и не ослаблять safety/control tests ради зелёного CI.

Если изменение только документационное — явно отметить это, но проверить, что ссылки/названия entrypoint и rollback flags соответствуют текущему коду.

## Правила по charge/control logic

- Chemistry, intent и condition независимы.
- `NORMAL`/`DIAGNOSTIC` не получают Recovery HV автоматически.
- В CV независимый сигнал — ток: `Imin -> ΔI`.
- В CC независимый сигнал — напряжение: `Vmax -> ΔV`.
- Нельзя применять CV current criterion к CC.
- Подтверждённая Mix delta запускает sticky 2h finish hold.
- AGM/CaCa/EFB fallback Mix windows: 10h / 20h / 20h.
- Temperature/telemetry/hardware safety всегда важнее finish logic.
- Output ON должен идти через fail-closed transactional boundary.

Перед спорным изменением стратегии открыть `CHARGE_STRATEGY.md` и сверить его с кодом/тестами.

## Температуры

- `temp_ext` = температура АКБ;
- `temp_int` = температура БП/контроллера.

Не использовать `temp_int` как evidence химического состояния батареи.

## UI/UX

- Не плодить новые dashboard messages без необходимости.
- Учитывать мобильную ширину Telegram.
- В CV карточке главным evidence остаются Imin/ΔI.
- В CC карточке главным evidence остаются Vmax/ΔV.
- Опасные/экспертные режимы не маскировать под обычную кнопку запуска.

## AI

- AI только объясняет/анализирует; он не является actuator authority.
- Не придумывать отсутствующие telemetry/capacity/condition.
- Не путать profile fallback deadline, finish hold и прогноз времени.
- В пользовательском тексте не показывать внутренние поля без необходимости.
