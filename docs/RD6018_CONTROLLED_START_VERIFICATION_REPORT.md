# RD6018 Controlled Start Verification

Статус: `CONTROLLED_START_VERIFIED`

Дата live-проверки: `2026-09-15` 14:39 UTC  
Режим: controlled hardware test, существующий V2 execution boundary.

## Safety gate

Перед START:

- battery voltage: `12.73 V`;
- requested voltage: `13.0 V` — не ниже Vbat;
- requested current: `0.4 A` — ниже лимита `0.9 A`;
- Output State Code V2: `0 / OFF`;
- Take Out V2: `off`;
- Safety Modbus Age: `4.8 s`;
- Protection Status Code: `0 / normal`;
- setpoint readback: `13.0 V / 0.4 A`;
- OutputStateConfidence: `ALLOW`.

## START evidence

START был выполнен через `HassClient.safe_enable_output()` и существующий
V2 safety/execution boundary. Нового hardware path не создавалось.

- request timestamp: `2026-09-15T14:39:00.518365+00:00`;
- Output ON confirmed: `2026-09-15T14:39:05.140411+00:00`;
- Output State Code V2: `1 / ON`;
- observed voltage: `12.77 V`;
- observed current: `0.39 A`;
- protection: `0 / normal`.

Текущий V2 physical path не экспортировал `session_id`, `trace_id` или
`decision_id`; значения зафиксированы как `UNKNOWN`, без synthetic identity.

## Mandatory ON interval

После фактического подтверждения ON выполнялось только наблюдение. Получено
10 snapshot-ов; максимальный наблюдаемый ток — `0.39 A`, protection fault не
обнаружен, Output State Code оставался `1`.

Фактический hold: `10.139 s` (`>= 10 s`). Нарушения лимитов не было.

## STOP evidence

- STOP request timestamp: `2026-09-15T14:39:15.279892+00:00`;
- ранний STOP: `false`;
- штатный `turn_off()` result: `true`;
- final Output State Code V2: `0 / OFF`;
- final current: `0.0 A`;
- final protection: `0 / normal`;
- final Modbus age: `5.9 s`.

## Ограничения evidence

Физический START/STOP path и readback подтверждены. Lifecycle START/STOP audit
chain не может считаться полной для V3, пока V2 не экспортирует identity и
decision provenance. Эти поля не реконструировались и не создавались задним
числом.

Физические команды выполнялись только в рамках явно разрешённого теста; V3
execution и ownership transfer не использовались.
