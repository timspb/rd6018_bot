# RD6018 V3 Program Identity Authority Model

Статус: **PROGRAM_IDENTITY_AUTHORITY_CLEAN**

## Single authority

`ProgramIdentityRegistry` в `application/charge_program/identity.py` является единственным владельцем:

- canonical program IDs;
- aliases;
- external names;
- alias-to-canonical resolution.

Current canonical identities:

| Canonical ID | Aliases/external names |
|---|---|
| `CALCIUM` | `CA_CA`, `KAK`, `Ca/Ca` |
| `EFB` | — |
| `AGM` | — |

## Direction

```text
external name
      |
      v
ProgramIdentityRegistry
      |
      v
canonical ID / Chemistry
      |
      v
ChargeProgram model
```

`ChargeProgram`/`BatteryProfile` хранят только canonical chemistry values. Внешнее имя при construction compatibility path делегируется в `ProgramIdentityRegistry`; domain model не содержит alias registry и не дублирует mapping.

`program_ids.py` оставлен только как compatibility export `ProgramIdResolver = ProgramIdentityRegistry`; собственного mapping там нет. Вторичный `aliases.py` удалён.

## Validation

Тесты проверяют alias resolution, stable canonical IDs, duplicate alias rejection, canonical-only model input и отсутствие secondary authority.

ChargeProgram behavior, GenericChargeEngine, PhaseLifecycle, SafetyDomain, UI, physical boundary и production wiring не менялись.
