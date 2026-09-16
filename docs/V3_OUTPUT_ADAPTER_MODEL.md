# V3 Output Adapter Model

## Граница

```text
ChargeIntent
      ↓
SafetyEngine
      ↓
SafeOutputIntent
      ↓
OutputAdapter
      X
physical RD/HA execution
```

`OutputAdapter` принимает только `SafeOutputIntent`. Он не принимает
`ChargeIntent`, не проверяет safety сам и не имеет доступа к recipe, strategy,
lease или ownership. В этом этапе присутствует только `MockOutputAdapter`,
который сохраняет intents в памяти и не выполняет I/O.

## SafeOutputIntent

`OutputAction` ограничен четырьмя domain-действиями: enable, disable,
set-voltage и set-current. Setpoints являются данными intent; значения и
ограничения не задаются output-слоем и не применяются им. Валидация формы
intent не является разрешением физического действия.

## Ownership

- ChargeStrategy и программы производят `ChargeIntent`.
- SafetyEngine проверяет recipe, measurements, phase и chemistry envelope.
- Только SafetyEngine/future safety boundary может сформировать
  `SafeOutputIntent`.
- Future OutputAdapter будет единственным местом физического исполнения.
- HA/RD/ESPHome, existing V2 wrappers и production controller остаются вне
  этого этапа.

## Migration blocker

Подключение physical adapter допустимо только после доказанных:

- V2 wrapper parity;
- readback parity;
- lease parity;
- verified-OFF parity;
- физического bench-теста на целевом узле.

Никаких production actuator calls этим commit’ом не добавлено.

## Отклонения от канона стратегии

- `SafeOutputIntent` пока не формируется автоматически из `SafetyDecision`.
- Физический OutputAdapter и V2 bridge намеренно отсутствуют.
- Safety wrappers production остаются отдельным владельцем до следующего
  migration gate.
