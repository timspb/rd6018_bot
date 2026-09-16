# V3 output bridge shadow

```text
SafetyDecision -> ExecutionPolicy -> SafeOutputIntent -> Shadow -> LegacyExecutionSnapshot
```

`V3OutputBridgeShadow` преобразует intent в снимок ожидаемого V2 исполнения и
фиксирует порядок операций. Для enable порядок: set V/I, protection,
readback, enable. Для disable: disable, verify-off, reset protection. Для
reset: reset OVP/OCP, readback.

`OutputParityComparator` сравнивает intent mapping с заранее полученным
legacy snapshot и возвращает `MATCH` или `MISMATCH`. Ни один класс этого слоя
не вызывает RD, HA, ESPHome, lease или production controller; `executed` здесь
отсутствует намеренно.

V1 UI остаётся отдельным migration-потоком.
