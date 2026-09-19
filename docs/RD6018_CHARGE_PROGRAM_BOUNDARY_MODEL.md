# RD6018 V3 Charge Program Boundary Model

Статус: **CHARGE_PROGRAM_BOUNDARY_READY**  
Режим: pure V3 domain modules; production V2 runtime не подключён.

## 1. Canonical model

`application/charge_program/models.py` предоставляет immutable `ChargeProgram`:

- `program_id`;
- `mode`: `AUTO` или `MANUAL`;
- `battery_profile` и canonical `chemistry`;
- ordered `phases`;
- voltage/current policies;
- timers;
- conditions;
- safety references.

Каждый параметр имеет `ParameterOwner`:

- `BATTERY_PROFILE` — chemistry-derived AUTO values;
- `MANUAL_PROGRAM` — explicit operator values;
- `SAFETY_POLICY` — ceilings, freshness and temperature references.

В модели нет controller, FSM implementation, HA, ESPHome, persistence или physical imports.

## 2. Resolution contract

```text
BatteryProfile + Mode + optional ManualProgramInput
                     |
                     v
             ChargeProgramResolver
                     |
                     v
              immutable ChargeProgram
```

`AUTO` поддерживает `CALCIUM`/`CA_CA`/`KAK`, `EFB`, `AGM`. `MANUAL` требует полного explicit `ManualProgramInput`; отсутствие параметров или передача Manual override в AUTO отклоняются.

## 3. AUTO programs

| Chemistry | Main voltage/current | Mix voltage | Mix authority |
|---|---:|---:|---:|
| CALCIUM / CA_CA | 14.7 V / min(7 A, 0.03C policy input) | 16.5 V | 20 h |
| EFB | 14.8 V / min(7 A, 0.03C policy input) | 16.5 V | 24 h |
| AGM | 15.0 V / min(8 A, 0.03C policy input) | 16.3 V | 10 h |

AUTO phases contain main and mix targets, delta condition, finish hold and safety references. These are domain values only; no execution is performed.

## 4. MANUAL program

Manual parameters are explicit and owned by `MANUAL_PROGRAM`:

- Main V/I;
- Mix V/I;
- ΔV/ΔI;
- hold hours;
- maximum Mix authority window.

The `Baic72` test fixture resolves to `manual:Baic72`. The resolver does not read `manual.yaml` and does not mutate the production Manual session; a future adapter may translate validated configuration into `ManualProgramInput`.

## 5. FSM boundary

The new contract is designed so a future V3 FSM consumes a complete `ChargeProgram`. It does not assemble chemistry checks, recipe values, timers or Manual overrides. This work does not modify the existing V2 FSM, which remains unchanged and disconnected.

## 6. Safety ownership

The program carries safety references and explicit ceilings; it does not make safety decisions and does not execute containment. Physical/safety execution remains outside this package.

There is deliberately no single anonymous `limit` field: voltage ceiling, current ceiling, temperature limit and telemetry freshness are separately named and owned.

## 7. Validation

`tests/test_workstream45_charge_program_boundary.py` covers:

- deterministic CALCIUM/CA_CA/KAK resolution;
- AUTO EFB and AGM completeness;
- Manual Baic72 resolution;
- invalid AUTO/MANUAL combinations;
- explicit ownership of parameters;
- absence of production wiring.

## 8. Scope confirmation

- `ChargeControllerV2` unchanged;
- legacy FSM unchanged;
- `bot.py`/production composition unchanged;
- node 101 untouched;
- no deployment, START/STOP, lease or physical action;
- no production import of the new package.
