# V3 physical bridge discovery

Этот этап только описывает read-only capability boundary:

```text
PhysicalBridgeAdapter -> HardwareCapability
                      -> HardwareSnapshot -> readback report
```

`HardwareCapability` фиксирует поддерживаемые действия, envelopes и resolution.
`HardwareSnapshot` содержит только состояние/измерения/уставки и не является
командой. `validate_readback()` сообщает mismatches без попытки исправления.

Test-only mapping fixtures переводят уже собранную V2 hardware-модель в V3
контракт. Интерфейс специально содержит только discovery, snapshot и health;
методов enable/disable/set/reset нет. Физический bridge, lease acquisition и
bench test остаются следующим отдельным gate.

V1 UI не входит в этот этап.
