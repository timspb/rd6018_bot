# RD6018 V3 Charge Program Behavioral Parity Audit

Статус: **BLOCKED**

Режим: read-only audit. Node 101, production runtime, V2 FSM и physical execution не затрагивались.

## Executive result

Очищенная V3 architecture сохраняет часть recipe data и базовые transition keys, но не сохраняет полную поведенческую семантику V2. Основные blockers:

1. `ChargeProgram.phases` содержит только `main` и `mix`; `PREP`, `DESULFATION`, `HOLD`, `SAFE_WAIT`, `DONE` представлены только как строки в transition rules и не имеют собственных phase contracts.
2. Delta/Hold представлены boolean condition keys, без start/end evidence, temperature dependency, confirmation policy и timeout behavior.
3. Generic engine при неизвестной phase возвращает отсутствие setpoints, но не восстанавливает полноценный lifecycle decision.
4. Safety policy проверяет только общие telemetry/containment/setpoint ограничения; отдельные OVP/OCP/OTP, emergency и hardware safety override не представлены в ChargeProgram/engine contract.

## 1. Program parity

### AUTO

| Program | Targets | Timers | Transitions | Result |
|---|---|---|---|---|
| CALCIUM | main 14.7 V / 7 A; mix 16.5 V; mix current min(12 A, 3% capacity) | main tail 3 h; Mix authority 20 h; finish hold 2 h | generic keys exist | PARTIAL |
| EFB | main 14.8 V / 7 A; mix 16.5 V; mix current min(12 A, 3% capacity) | main tail 3 h; Mix authority 24 h; finish hold 2 h | generic keys exist | PARTIAL |
| AGM | main 15.0 V / 8 A; mix 16.3 V; mix current min(12 A, 3% capacity) | main tail 3 h; Mix authority 10 h; finish hold 2 h | generic keys exist | PARTIAL |

Все AUTO programs фактически имеют phase tuple `("main", "mix")`. Общие transitions объявлены для `prep`, `desulfation`, `hold`, `safe_wait`, `done`, но соответствующие Phase objects отсутствуют.

### MANUAL — Baic72 example

Проверенный пример: `Baic72`, chemistry alias `CA_CA`, explicit operator values.

- phases: `main`, `mix`;
- targets: explicit manual V/I;
- timers: manual hold и manual max-mix authority;
- transitions: main → mix → hold → safe_wait → done;
- Delta conditions: только `delta_confirmed` для engine transition, несмотря на наличие отдельных descriptive `delta_voltage`/`delta_current` conditions.

Result: **PARTIAL**. Battery identity сохраняется в `program_id`, но это не доказывает полноценную V2 Manual lifecycle semantics.

## 2. FSM contract

Ожидаемая lifecycle-модель:

```text
PREP -> MAIN -> DESULFATION/MIX -> HOLD -> SAFE_WAIT -> DONE
```

Фактическая модель:

- `PREP -> MAIN` работает через transition rule `__entry__`;
- `MAIN -> MIX` работает при `main_complete`;
- `MAIN -> DESULFATION` может быть выдан как next phase, но `desulfation` не является program phase;
- `MIX -> HOLD` работает при `delta_confirmed`, но `hold` не является program phase;
- `HOLD`, `SAFE_WAIT`, `DONE` не имеют Phase policy;
- при неизвестной phase engine выдаёт no-setpoint explanation, а не полноценное состояние/phase decision.

Статус FSM parity: **BLOCKED**.

## 3. Delta/Hold audit

### Что присутствует

- AUTO condition text для `mix_delta`;
- Manual descriptive `delta_voltage` и `delta_current` conditions;
- `delta_confirmed` transition key;
- AUTO finish hold timer 2 h;
- Manual hold timer из operator input;
- Mix authority timers 20/24/10 h для AUTO.

### Что отсутствует

- отдельные CV current-based и CC voltage-based delta algorithms;
- start evidence и end evidence;
- spaced confirmation policy;
- sticky accepted hold semantics;
- distinction between active-Mix authority timeout и successful completion;
- timeout result `MIX_TIMEOUT -> STOP_AND_DIAGNOSE -> verified OFF`;
- temperature dependency/compensation;
- safety interruption and recovery semantics;
- durable active-time accounting.

Статус Delta/Hold parity: **BLOCKED**.

## 4. Safety override

`application/execution_intent/policy.py` проверяет:

- enabled safety policy;
- containment state;
- telemetry state `UNKNOWN/STALE/INVALID`;
- maximum voltage/current;
- positive setpoints.

Это полезная intent-level gate, но не эквивалент V2 safety authority.

Не представлены в ChargeProgram/GenericChargeEngine как отдельные authoritative overrides:

- OVP;
- OCP;
- OTP/thermal rules;
- readback mismatch;
- hardware protection status;
- emergency path;
- lease/watchdog containment.

При stale telemetry engine не создаёт setpoints, но сам не создаёт shutdown/containment decision. Это соответствует архитектурному запрету engine на physical/safety action, однако safety parity возможна только после явного Safety Domain contract.

Статус safety parity: **BLOCKED** до доказанного внешнего Safety Domain integration contract.

## 5. Findings

| ID | Finding | Severity | Required follow-up |
|---|---|---:|---|
| CP-001 | Lifecycle phases absent as `Phase` objects | BLOCKER | Add program-owned phase contracts or explicit lifecycle contract |
| CP-002 | Delta/Hold reduced to booleans/labels | BLOCKER | Model evidence, confirmations, sticky hold and timeout semantics |
| CP-003 | Mix timeout semantics absent | BLOCKER | Model abnormal termination separately from successful completion |
| CP-004 | Temperature and safety interruption absent from program contract | BLOCKER | Define Safety Domain inputs/overrides without physical calls |
| CP-005 | OVP/OCP/OTP/emergency/lease not represented by engine | BLOCKER | Add explicit safety decision boundary and parity tests |
| CP-006 | Manual Delta fields are descriptive but not evaluated by generic transition | WARNING | Bind condition keys to program-owned evaluator contract |

## Conclusion

`CHARGE_PROGRAM_BEHAVIORAL_PARITY_VALIDATED` не выдаётся.

Итоговый статус: **BLOCKED**.

Паритет recipe targets частично подтверждён, но текущая V3 ChargeProgram architecture ещё не является поведенчески эквивалентной V2. Исправления и runtime changes в рамках этого audit не выполнялись.
