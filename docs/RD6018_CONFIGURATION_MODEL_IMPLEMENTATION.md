# RD6018 ConfigurationModel — Phase 6.4

Phase 6.4 добавляет validated representation поверх inventory. Это не loader
production и не изменение текущей конфигурации.

## Model

`application.configuration_model.ConfigurationModel` создаётся из
`ConfigurationAuthority` и набора read-only source mappings. Он предоставляет
девять секций:

- `ChargeConfig`
- `StrategyConfig`
- `SafetyConfig`
- `ContainmentConfig`
- `LeaseConfig`
- `ExecutionConfig`
- `TransportConfig`
- `UIConfig`
- `PersistenceConfig`

Каждая зарегистрированная запись содержит `type`, `default`, `validator`,
`source` и `owner`. Значение source сохраняется в `ConfigurationValue` для
аудита происхождения.

## Migration adapters

`YamlSourceAdapter`, `PythonConstantsAdapter` и `EnvironmentSourceAdapter`
только читают старые источники:

- YAML разбирается в mapping с явным canonical-key mapping;
- Python читается через AST и `literal_eval`, без импорта runtime-модулей;
- environment принимается как mapping, что позволяет тестировать его без
  чтения deployment secrets.

Adapters не пишут файлы, environment, SQLite, HA, ESPHome или physical layer.

## Resolution rules

1. Значения приводятся к типу параметра и проходят validator.
2. Одинаковые значения из нескольких источников принимаются.
3. Разные значения дают `ConfigurationConflictError` — silent precedence нет.
4. Required parameter без источника даёт `ConfigurationMissingError`.
5. Не найденный необязательный параметр использует только задокументированный
   default и помечается source `default`.

## Runtime boundary

Новый model не импортируется production bootstrap и не подключён к START,
ACTIVE, Telegram, HA, ESPHome, persistence или physical execution. Текущие
YAML/Python/env источники не изменяются. Значения в schema взяты из Phase 6.3
inventory; спорные параметры должны пройти отдельный parity review до будущего
подключения.
