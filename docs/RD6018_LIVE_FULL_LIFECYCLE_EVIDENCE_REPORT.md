# RD6018 Live Full Lifecycle Evidence Capture — WORKSTREAM 80

Статус: `PARTIAL_OBSERVATION` — observer armed, waiting for natural START

## Current armed observation

- observation_id: `ws81-20260915T130058Z`
- fresh idle gate: PASS (`stopped`, output/current `0.0/0.0`)
- capture window: `2026-09-15T13:00:58Z`–`13:01:07Z` UTC
- natural `idle → START/active`: NOT OBSERVED
- physical commands: none

## Причина

Полный lifecycle ещё не начат: idle gate теперь подтверждён и observer armed,
но естественный новый START в capture window не произошёл.

Последний доступный evidence-артефакт WS74 имеет статус `ARMED_WAITING` и
фиксирует, что переход `active → idle` не наблюдался. Предыдущая live
observation также фиксировала активный V2 charge state. Свежего подтверждения
`V2=idle` в этом запуске нет.

## Capture state

| Требование | Результат |
|---|---|
| Observer active before START | NOT PROVEN |
| V2 idle before START | NOT PROVEN |
| Natural session start | NOT CAPTURED |
| Program selection | NOT CAPTURED |
| Phase transitions | NOT CAPTURED |
| Delta/Hold | NOT CAPTURED |
| Termination/STOP/DONE | NOT CAPTURED |
| V2/V3 parity and audit events | NOT CAPTURED |

## Integrity rules

Синтетические события, synthetic identity и timeline reconstruction не создавались.
Legacy identity остаётся `UNKNOWN`. Existing historical evidence не выдана за
новый lifecycle.

Не выполнялись START/STOP, изменение параметров, lease operations, ownership
transfer, deployment или physical execution.

## Следующее допустимое окно

1. Активировать read-only observer до естественного перехода V2 в `idle`.
2. Зафиксировать fresh idle snapshot и observation metadata.
3. Собирать только реально наблюдаемые события до DONE/STOP/termination.
4. Повторить WS80; статус `FULL_LIFECYCLE_EVIDENCE_CAPTURED` возможен только
   после наличия полной непрерывной цепочки.
