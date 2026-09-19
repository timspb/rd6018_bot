# RD6018 Canary Gate Scope Review — WORKSTREAM 95

Статус: `OBSERVE_ONLY_READY`

Цель review — не разрешение Canary execution, а корректное разделение gates
по режимам. Код, ownership, lease и production не изменялись.

## 1. OBSERVE_ONLY

`OBSERVE_ONLY` означает: V3 читает, нормализует, сравнивает и показывает
состояние; V2 сохраняет все decision/physical права.

### Обязательные требования

| Requirement | Result | Evidence |
|---|---|---|
| telemetry freshness | PASS for current HA/RD read path | свежий read-only snapshot: RD values/output/protection/timestamps |
| source availability | PASS for observation sources | HA доступен; ESPHome endpoint reachable; V2 state/evidence sources описаны |
| parity visibility | PASS | V2 vs V3 fields and `MATCH/EXPECTED_DIFFERENCE/DIVERGENCE/UNKNOWN` visible |
| no side effects | PASS | no commands, writes, lease changes or physical execution |

### Не является обязательным gate

Для `OBSERVE_ONLY` не требуются:

- execution approval;
- lease ownership or renewal authority;
- physical adapter readiness;
- physical readback verification for a V3 command;
- V3 decision or execution ownership.

Их отсутствие должно отображаться оператору как capability limitation, но не
блокировать read-only dashboard/shadow observation.

## 2. APPROVED_CANARY

`APPROVED_CANARY` — отдельный более строгий режим. Для него обязательны:

- explicit approval с owner, scope, expiry и revoke conditions;
- fresh lease evidence и однозначный lease owner;
- execution intent validation;
- physical execution acceptance и readback verification;
- rollback owner/procedure;
- identity-correlated session/trace evidence;
- safety/containment readiness.

Эти требования остаются blockers для `APPROVED_CANARY`, но не смешиваются с
`OBSERVE_ONLY` gate.

## 3. Current decision

V3 может работать в `OBSERVE_ONLY` как read-only observer:

```text
HA/RD/ESP/V2 observations
        |
        v
V3 normalization and parity
        |
        v
Operator visibility only
```

В текущем live snapshot Output был `OFF`, RD `0 V / 0 A / 0 W`, protection
`normal`, поэтому никаких физических действий для подтверждения режима не
требовалось и не выполнялось.

`OBSERVE_ONLY_READY` не означает `APPROVED_CANARY`, `V3_CANARY_REVIEW_READY`
или physical readiness.

## 4. Scope invariants

- V2 остаётся production и physical owner.
- V3 не создаёт commands и не вызывает execution boundary.
- Lease только наблюдается.
- Missing/stale telemetry показывается как `UNKNOWN` и снижает confidence.
- Parity divergence сохраняется как evidence, но не меняет V2.

