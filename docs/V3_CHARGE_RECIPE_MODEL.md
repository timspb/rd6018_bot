# V3 Charge Recipe / Profile Model

## Назначение

Этот слой хранит параметры зарядной стратегии отдельно от алгоритма. Он не
управляет HA, Telegram, RD6018, Output, lease или SafetyEngine и не подключён
к production controller.

Поток данных:

```text
factory recipe
      ↓
user override (whitelist)
      ↓
validated recipe
      ↓
BatteryProfile
      ↓
ChargeStrategy
      ↓
ChargeIntent
```

## Factory recipes

`RecipeRegistry` предоставляет профили `AGM`, `EFB`, `CA_CA`, `FLOODED` и
`CUSTOM`. Производственные имена преобразуются на границе через явный mapping:

| Production label | Domain chemistry |
| --- | --- |
| `AGM` | `AGM` |
| `EFB` | `EFB` |
| `CA_CA` | `CALCIUM` |
| `FLOODED` | `CALCIUM` |
| `CUSTOM` | `CALCIUM` base, затем явные overrides |

`CUSTOM` не является отдельной химией и не создаёт отдельную программу. Для
создания пользовательского custom-профиля требуется хотя бы один разрешённый
override; пустой custom DTO отклоняется.

Рецепт содержит только данные MAIN, Recovery, MIX CC/CV, fallback и активного
бюджета MIX. Числа находятся в `runtime/charge/profiles/recipe.py` как factory
data, а не внутри переходов стратегии.

## Inheritance and validation

`apply_recipe_override` создаёт новый immutable-рецепт поверх factory-рецепта.
Разрешены только безопасные пользовательские поля:

- `mix.cc.delta_voltage`;
- `mix.cv.delta_current`;
- `mix.cc.hold_seconds`;
- `mix.cv.hold_seconds`.

Recovery budget, mandatory limits и другие поля политики не могут быть удалены
или изменены через этот boundary. `ChargeRecipeValidator` отклоняет пустую
химию, некорректный DTO, неизвестную химию и недопустимые значения.

`RecipeDTO` — только serialization boundary для будущего UI. Storage и
Telegram пока не подключены.

## Ownership and migration status

- Profiles владеют параметрами рецептов.
- ChargeStrategy владеет алгоритмическими переходами.
- ChargeEngine создаёт intent.
- SafetyEngine остаётся следующим защитным boundary.
- Production controller, output и legacy runtime не изменены.

Следующий шаг — отдельное решение о миграции потребителей recipe layer и
проверка эквивалентности на representative vectors; автоматическое включение в
production этим этапом запрещено.

## Отклонения от канона стратегии

- `CUSTOM` пока использует `CALCIUM` как базовый профиль и не имеет отдельного
  набора chemistry-параметров.
- Storage/SafeWait остаются за отдельным post-charge boundary.
- Recipe layer пока не подключён к production controller.
