# RD6018 V3 Migration Exit Criteria

Status: `EXIT_CRITERIA_DEFINED`

Scope: условия безопасного удаления временных migration bridges после WS137.
Документ не удаляет компоненты, не меняет execution path и не передаёт V3
physical ownership.

## Canonical invariant

`V3 Decision Plane → Safety/Approval → ExecutionIntent → ExecutionPort → V2 Physical Owner → existing adapters → RD6018`

V2 остаётся единственным production physical owner. Любое удаление bridge
допустимо только после подтверждения эквивалентного V3/V2 пути и сохранения
rollback на V2.

## Removal decision protocol

Удаление выполняется отдельным change set после review владельца компонента.
Для каждого bridge обязательны:

- focused tests и полный regression suite;
- compileall и `git diff --check`;
- runtime proof на deployment-копии без hardware action;
- parity proof для заменяемого поведения;
- ownership proof: один physical owner, без bypass path;
- подтверждённый rollback и отсутствие незакрытых consumers.

Решение об удалении принимает владелец соответствующей границы совместно с
владельцем V2 physical runtime; операторский/UI слой не может удалить bridge
самостоятельно.

## Bridge exit matrix

| Category / component | Current role | Removal prerequisites | Required evidence | Decision owner |
|---|---|---|---|---|
| `application/execution_port.py` и связанные execution-port migration layers | Единственная V3→V2 execution boundary | Не удалять до появления эквивалентной стабильной boundary; все callers переведены; V2 owner сохранён | boundary/ownership tests, intent-required tests, dry-run и V2 parity, rollback proof | V3 execution owner + V2 physical owner |
| `application/manual_execution_boundary.py` | Переходный manual intent → `ExecutionPort` bridge | Все manual start/stop/error/cooling/settings paths подтверждённо идут через canonical port; direct setter scan пуст | manual boundary tests, identity/audit correlation, no-direct-hardware proof, controlled review | Manual authority owner + V2 physical owner |
| `application/manual_identity_integration.py` / `manual_phase_lifecycle.py` | Manual lifecycle identity и phase decision boundary | Все новые manual sessions имеют identity; resume semantics покрыты; legacy restore остаётся explicit `AMBIGUOUS` | identity propagation, lifecycle, replay, session isolation, no-fake-event tests | Lifecycle/domain owner |
| `application/v2_start_runner_adapter.py`, `v2_start_transaction_adapter.py`, `v2_start_event_context.py` | Transitional V2 START adapters и identity context | Единственный START authority определён; все callers используют canonical start contract; no duplicate START; rollback на V2 проверен | start authority/orchestration tests, duplicate protection, identity/audit trace, V2 parity | Start authority owner + V2 runtime owner |
| `application/production_start_runner.py`, `production_start_route.py`, `production_start_execution_port.py` | Совместимость production START route с V2 owner | Production route имеет один execution boundary; compatibility callers удалены/заменены; no direct hardware path | production isolation, route/boundary tests, exact V2 runtime proof, rollback | V2 production owner |
| `application/legacy_domain_adapter.py` | Compatibility seam для legacy domain inputs | Выполнено в WS142: consumers переведены на canonical `runtime.charge` imports, production references отсутствуют | domain/import isolation, shadow parity, regression tests | V3 domain owner |
| `application/legacy_ui_boundary.py` | Read-only legacy UI compatibility adapter | Выполнено в WS141/WS142: production imports отсутствуют, provider использует canonical observation source | UI source purity, scenario snapshots, rendering/parity tests | Operator UI owner |
| `runtime/ui/legacy_shadow/**` | UI parity/shadow mapping | Выполнено в WS141: production surface удалён, parity fixtures сохранены в tests | UI parity report, fixture replay, no-runtime-read tests | Operator UI owner |
| `runtime/charge/adapters/legacy.py` | Removed in WS144; parity mapping is test-only | parity fixture coverage retained; no production decision consumer | behavioral parity, shadow coverage, divergence review | Charge domain owner |
| `runtime/charge/shadow/**` и `application/*shadow*` | Read-only V2/V3 parity and replay | Утверждены retention policy и replacement audit trail; no execution imports | live/shadow parity, replay, import isolation, evidence retention | V3 observability owner |
| `runtime/output/bridge/PhysicalBridgeExecutor` | Obsolete compatibility executor | Выполнено в WS143: class/export удалены; gate/readback contracts остаются без execution authority | ownership scan, no-write tests, import inventory, diff review | V2 physical owner + safety owner |
| `runtime/output/**` contracts/policy/simulation/verification | Non-owning contracts, simulation and verification surfaces | Для каждого файла доказано отсутствие active consumer или наличие canonical replacement; no write capability | static write scan, simulation tests, compile/import tests | Execution boundary owner |
| `runtime/physical/connectors/**` и `transports/**` | Read/discovery/readback adapters; write-shaped surfaces fail closed | Readback/verification consumers migrated; any write-capable API either removed or explicitly V2-owned adapter contract | connector/readback tests, no-write proof, physical ownership assertion | V2 physical owner |
| `physical_test_control*.py` | Explicit opt-in controlled validation surface, not V3 production path | Отдельный controlled-test review, replacement/retention decision, operator runbook and rollback | exact node/package bench evidence, gated import tests, no default activation proof | Hardware test owner + V2 physical owner |
| `bot_legacy.py` | Emergency rollback entrypoint | Replacement emergency path proven; rollback artifact retained; production owner signs off | recovery drill, service/runbook proof, rollback trace | Production/V2 owner |

## Category-specific exit criteria

### Execution bridges

Удаление manual/execution bridge разрешено только когда input остаётся
`ExecutionIntent`, safety/approval остаются обязательными, а единственный
физический путь проходит через `ExecutionPort` к V2 owner. Нельзя заменять
bridge прямым вызовом HassClient, connector или transport.

### START/lifecycle bridges

Сначала требуется доказать единый START authority, связанный с
`session_id`, `trace_id`, lifecycle event и audit. Legacy active state без
identity наблюдается как `UNKNOWN`/`AMBIGUOUS`; post-factum identity и fake
START не являются заменой bridge.

### Legacy domain/UI bridges

Удаление возможно только после полного переноса consumers на canonical
V3 models. Исторические данные могут оставаться replay fixtures, но не
должны читаться операторским UI как runtime source.

### Physical validation surfaces

Physical test surfaces нельзя считать безопасными к удалению только по
отсутствию вызовов в обычном запуске. Для них нужны статический ownership
proof, отсутствие write capability в production composition и отдельная
подтверждённая процедура hardware validation.

### Rollback surface

`bot_legacy.py` остаётся до тех пор, пока новый путь не имеет проверенного
emergency rollback, сохраняющего V2 safety/ownership semantics. Удаление
rollback entrypoint требует отдельного release decision.

## Cleanup completed

WS141/WS142 удалили production UI shadow surface, legacy UI boundary и legacy
domain import seam после
подтверждения отсутствия production consumers. `OperatorSnapshotProvider`
теперь получает данные через `OperatorObservationSource`; parity fixtures
остались только в test-only helper.

## Ready for future cleanup

К будущему cleanup подготовлены инвентарь и критерии для:

- legacy charge adapter после закрытия parity review;
- legacy charge/UI shadow mappings после закрытия parity review;
- transitional START adapters после стабилизации единого START authority.

Это не означает разрешение удалить их в текущем change set.

## Must not be removed now

До отдельного решения нельзя удалять или менять:

- `runtime/v2_runtime.py`, `HassClient`, V2 safety guards и lease semantics;
- `application/execution_port.py`;
- `manual_execution_boundary.py` и identity/lifecycle bridges, пока есть active consumers;
- readback/connectors, необходимые для verification и observation;
- `physical_test_control*.py` без отдельного controlled-test review;
- `bot_legacy.py` без доказанного rollback replacement.

## Validation performed for this baseline

Read-only focused validation in the isolated release worktree:

- WS133 ownership tests: `3 PASS`;
- WS124 execution-plane tests: `5 PASS`;
- WS113B manual boundary tests: `3 PASS`;
- production physical isolation tests: `2 PASS`;
- phase cleanup contracts: `4 PASS`;
- execution boundary contracts: `6 PASS`;
- total focused tests: `23 PASS`;
- `compileall`: `PASS`;
- `git diff --check`: `PASS` (line-ending warnings only).

No code, runtime configuration, ownership, deployment or hardware state was
changed for WS138. The document itself is the only new file from this
workstream; no WS138 commit was created.
