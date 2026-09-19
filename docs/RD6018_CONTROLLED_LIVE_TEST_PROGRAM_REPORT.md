# RD6018 Controlled Live Test Program — WORKSTREAM 101

Финальный статус: `STOPPED_WITH_REASON`

Режим: `CONTROLLED_TEST_MODE`, существующий V2 physical owner. Тест остановлен
до физического включения по обязательному safety rule: stale telemetry.

## Preflight snapshot

Read-only snapshot перед попыткой Test 2:

```text
battery voltage: 12.73 V
requested voltage: 13.0 V (not below battery voltage)
requested current: 0.5 A (<= 0.9 A limit)
output: OFF
measured: 0.0 V / 0.0 A / 0.0 W
protection: code 0, normal, tripped=false
OVP/OCP readback: 16.7 V / 12.0 A
setpoint readback: 13.0 V / 0.4 A
```

## Attempted Test 2 — low-current start

The existing `safe_enable_output()` path was invoked with 13.0 V / 0.5 A,
using the already-read protection values. The safety coordinator rejected the
enable before Output ON because the HA switch telemetry was stale:

```text
switch stale age: 3846.6 s
allowed maximum: 20.0 s
enable result: disabled
reason: required live telemetry is missing or invalid
```

After snapshot:

```text
output: OFF
measured: 0.0 V / 0.0 A / 0.0 W
output state code: 0
protection: code 0, normal, tripped=false
CC/CV: CC=false, CV=true
```

No setpoint write, Output ON, current change or physical execution occurred.

## Tests 1–6 disposition

| Test | Status | Reason |
|---|---|---|
| START/STOP boundary | NOT_RUN | safe start gate failed before lifecycle/physical action |
| low-current start | STOPPED | stale switch telemetry; fail-closed rejection |
| voltage/current change | NOT_RUN | no verified active test session |
| CC/CV transition | NOT_RUN | Output remained OFF |
| MIX/HOLD | NOT_RUN | no active lifecycle created |
| STOP path | NOT_RUN | no start was accepted; no STOP command issued |

## V2/V3 and audit evidence

V2 remained the physical owner. V3 was not given execution authority; no V3
physical request was created. Because no start was accepted, no real
`SessionStarted`, `ExecutionIntent`, physical verification or completion event
was synthesized. Existing legacy identity gaps remain unchanged.

## Safety conclusion

The test program correctly stopped on stale telemetry, before any physical
transition. Required recovery is fresh verified telemetry, followed by a new
preflight; this report does not authorize bypassing the safety coordinator.

