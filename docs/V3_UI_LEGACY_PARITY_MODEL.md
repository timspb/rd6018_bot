# V3 UI legacy parity shadow

`LegacyUISnapshotAdapter` принимает только заранее подготовленное состояние
V1 display surface. `UIParityComparator` сравнивает его с V3
`RuntimeUISnapshot` и возвращает `MATCH`, `MISSING` или `MISMATCH`; rendering,
Telegram handlers и callbacks не вызываются.

Сопоставляются stage/phase, V/I/T, timers, messages, warnings/faults, battery
status и output state. V3 дополнительно способен показывать recipe, limits,
transition evidence, подтверждённые Vmax/Imin, delta/hold и current
containment — эти поля не считаются расхождением, если они отсутствовали в V1.

V1 UI остаётся production-каноном на отдельном этапе миграции. Этот shadow не
меняет его оформление и поведение и не создаёт ChargeIntent/Output action.
