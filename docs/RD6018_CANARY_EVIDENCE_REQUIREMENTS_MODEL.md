# RD6018 Canary Evidence Requirements Model — WORKSTREAM 100

Статус: `CANARY_EVIDENCE_MODEL_READY`

Модель определяет gates перехода между режимами. Она не выполняет physical
control, START/STOP или ownership transfer.

## 1. OBSERVE_ONLY

Минимально достаточный evidence package:

- свежая telemetry с timestamp, source, freshness и confidence;
- source health/availability для используемых HA/RD/ESP/V2 readers;
- read-only operator UI snapshot: card, graph, log и diagnostics separation;
- V2/V3 shadow parity visibility с `MATCH`, `EXPECTED_DIFFERENCE`,
  `DIVERGENCE`, `UNKNOWN`;
- доказательство отсутствия commands/writes/lease mutation.

Для этого режима не обязательны lease ownership, execution approval, physical
readback of a V3 command или полная START-to-STOP lifecycle chain. Missing data
должно отображаться как `UNKNOWN`, а не блокировать сам observer, если source
health и telemetry freshness достаточны для безопасного наблюдения.

## 2. SHADOW_DECISION

Минимальные обязательные требования:

1. Реальные correlated observations минимум для `PREP`, `MAIN` и `MIX` или
   фактических фаз, которые реально использует текущий V2 program.
2. Для каждой покрытой фазы: program, phase, targets, telemetry, safety,
   V2 state, V3 decision, parity result и trace/timestamp provenance.
3. Минимум один полный decision-consistent observation cycle для выбранного
   program, либо явно documented partial coverage.
4. Реальные divergence classification и replayable evidence.
5. Fail-closed поведение stale/missing telemetry и identity mismatch.
6. Отсутствие влияния V3 на V2 и physical owner.

HOLD и DONE обязательны, если соответствующая программа действительно до них
доходит в обычном lifecycle и решение о переходе/завершении входит в scope
shadow comparison. Они не должны синтезироваться; при отсутствии естественного
наблюдения остаются coverage gap и `UNKNOWN`.

Рекомендуется несколько циклов и покрытие всех программ, но это
`NICE_TO_HAVE`, пока scope явно ограничен одним program/phase set.

## 3. APPROVED_CANARY

Обязательные gates:

- explicit approval: `approval_id`, owner, mode, scope, constraints, expiry,
  revoke и rollback conditions;
- fresh lease evidence и однозначный lease owner;
- identity-bearing session: `session_id`, `trace_id`, `decision_id`;
- safety/containment evidence и stale/missing fail-closed behavior;
- rollback procedure, owner, trigger и authority revoke path;
- physical adapter/readback verification proven separately на approved bench;
- intent validation, approval binding и duplicate/parallel execution guard;
- complete audit chain для решения и handoff;
- V2 fallback remains available and tested.

Без этих gates `APPROVED_CANARY` запрещён, даже если shadow parity равен
`MATCH`.

## 4. Blocker vs NICE_TO_HAVE

### BLOCKER

- unknown or stale safety/lease state для canary scope;
- missing identity или conflicting session/trace;
- unexplained safety or decision divergence;
- отсутствие rollback/revoke path;
- отсутствие approval;
- physical readback/verification not proven;
- любой V3 physical bypass или duplicate owner;
- synthetic/fake lifecycle evidence;
- V3 influence on V2 before approval.

### NICE_TO_HAVE

- дополнительные независимые cycles сверх минимального scope;
- полное покрытие редких программ и редких фаз;
- расширенная UI analytics детализация;
- исторические графики без влияния на current-session evidence;
- дополнительные operator explanations при уже достаточной provenance.

## 5. Transition rule

```text
OBSERVE_ONLY
  --fresh telemetry + source health + parity visibility-->
SHADOW_DECISION
  --identity + approval + lease + rollback + verification-->
APPROVED_CANARY
```

Каждый переход требует явной gate evaluation. Никакой переход не происходит
только из-за наличия unit tests или совпадения одного live snapshot.

