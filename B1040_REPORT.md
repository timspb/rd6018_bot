# B1040 — Module Manager и демонтаж AI

**Дата:** 2026-11-27
**Репозиторий:** `timspb/rd6018_bot`
**База:** `cf5edffeda2a3bc1d4e37374d42861f4d9c9d131`
**Источник:** отдельная чистая копия `E:/CODEX/My_Local/RD6018_B1040_WORK/optional-module-manager`
**Назначение:** реализовать управляемое подключение/отключение необязательных модулей без нового двигателя, физического владельца или центра управления зарядкой.

## Реализация

- `runtime/optional_modules.py` — явный каталог `ModuleSpec` и небольшой `ModuleManager` (status, install, install_all, installed, shutdown), конфигурация `RD6018_MODULE_AI` и read-only `python -m runtime.optional_modules status`.
- `integrations/ai/module.py` — собственный installer AI. `bot.ProductionComposition` теперь вызывает общий `modules.install_all`, а не импортирует AI напрямую. Необязательный UI скрывается, если пакет удалён, отключён или `V2_UI=0`.
- `runtime/production_runtime.py`, `charge_controller.py`, `application/operator_snapshot_provider.py`, `application/production_session_extensions.py` — ленивые AI exports и существующий нейтральный read-only fallback. Отсутствие AI не превращается в ошибку Safety, не влияет на рецепты и управляющие алгоритмы.
- HMI, Telegram-команды и справка не отображают AI-функции при его отсутствии/отключении; при включённом установленном AI прежние обработчики и представление сохранены.
- Core-модули (Safety Authority, Charge Engine, единственный ExecutionPort, sessions/restore, ESP lease) не входят в каталог и не могут быть отключены менеджером. Менеджер не разрешает hot-unload, самостоятельное удаление файлов, самостоятельный install в сервис или физические команды.

## Приёмка

- `tests.test_optional_module_manager`: **9/9 PASS**, в том числе создание изолированной копии исходников **без каталога `integrations/ai`**, реальный импорт/композиция `bot` без AI, нейтральные операторские снимки, отсутствие AI UI/команды/справки, enabled/disabled, idempotent install, shutdown и CLI-status.
- `tests.test_v3_ui_analysis_cutover`, `test_v3_l002_composition_inventory`, `test_operator_hmi`, `test_telegram_runtime_adapter`, `test_production_entrypoint`: **81/81 PASS** с установленным и включённым AI.
- Профильные тесты отключённого AI для физического ExecutionPort, managed safety, physical contracts, session recovery, modular architecture и production entrypoint: **100/100 PASS** (`RD6018_MODULE_AI=0`).
- Первая совместная регрессия AI, UI, composition и ExecutionPort: **55/55 PASS** (до дополнительного скрытия AI UI; отдельные позднейшие 9/81/100 покрыли изменённые границы). Числа описывают отдельные запуски, а не число уникальных тестов.
- Канон P0–P9 расширен одним проверяемым требованием P7: **99/104** source/documentary, остаётся прежних пять P3/P8 физических/релизных HOLD. Все пять канонических блоков синхронизированы.
- Дополнительные инструкции и ограничения: `docs/architecture/OPTIONAL_MODULE_LIFECYCLE.md`, обновлённые OWNERSHIP и AGENTS.

**Не выполнялось:** node104, RD/ESP/HA, сетевой AI-запрос, реальный Output/уставки, прошивка, service restart, production install/rollback. Реальное функционирование зарядника после физического удаления AI на node104 не заявляется. Это проверенная source/fake демонтируемость при следующем обновлении и запуске.
