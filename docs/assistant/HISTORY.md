# История Проекта Для Ассистента

> Исторические заметки. Этот файл больше **не** является главным source of truth по стратегии.
>
> Актуальная иерархия: `docs/assistant/README.md`.

## 2026-08-30 — полный аудит V1 перед продолжением V2

Перед дальнейшей переделкой Pb Recovery V2 был отдельно разобран production V1 на `main` commit:

```text
8d3e2af9c2f16721f3303579f12d4f39bcc98a13
```

Зафиксированы отдельные документы:

- `V1_BEHAVIORAL_AUDIT.md` — фактическая архитектура/логика V1;
- `V2_DECISION_LOG.md` — принятые и отклонённые решения V2;
- `V2_OPEN_QUESTIONS.md` — вопросы, которые ещё не решены;
- `CHARGE_STRATEGY.md` — короткая текущая стратегия;
- `PB_RECOVERY_V2.md` — архитектура V2.

Главный вывод аудита: V1 — это не только `ChargeController`. Поведение складывается из FSM, Telegram/operator paths, actuator sequencing, HA/readback, persistence/restore, watchdogs, manual/unmanaged operation и diagnostics.

### Ключевые решения после аудита

- Vin — здоровье входного БП, а не Pb-FSM authority.
- Абсолютный V2 software voltage ceiling — 17.5 V; recipe ceilings остаются ниже без explicit expert authorization.
- `BAT_MODE` — наблюдение, не разрешение запуска.
- Нужно различать commanded / configured-readback / measured values.
- При `Vbat < ~12 V` ток должен оставаться маленьким (PREP-like ~0.01C).
- Main normal-tail и stuck plateau — разные evidence-механизмы.
- Ca/EFB recovery attempts — общий session-wide budget; progress не сбрасывает count.
- После исчерпания Ca/EFB recovery budget следующий confirmed stuck plateau ведёт в final Mix.
- AGM намеренно более консервативен и не копирует Ca/EFB recovery policy.
- V1 Ca/EFB 72h Main->Mix признан отдельным intentional fallback, а не найденным багом.
- SAFE_WAIT 2h — maximum wait, не fault timeout.
- Mix completion: CV `Imin->ΔI`, CC `Vmax->ΔV`, 3 spaced confirmations, затем sticky 2h hold.
- V2 Mix fallback maxima: Ca 20h / EFB 24h / AGM 10h.
- Done = Storage/float ~13.8V/1A с Output ON.
- Cooling = пауза chemistry clocks/evidence continuity с durable persistence, а не новая химическая evidence-stage.
- Manual — реальный поддерживаемый режим; exact V2 schema ещё проектируется.
- Bank/cell fault должен быть evidence-based; actuator authority для confirmed fault ещё не определён.
- Временный heuristic `plateau >~1%C => automatic HV veto` отклонён как слишком грубый.

### Реализация V2 после аудита

Commit `1bd67cb875afeed4ae722a4e5fd335d6eecdd8cd`:

- corrected RD6018 telemetry foundation;
- freshness/readback model;
- OPP protection decode;
- Vin removed from charge authority;
- 17.5V absolute envelope;
- fail-closed setpoint/readback/output transaction.

Commit `abfcbda97b947a73a474a3c11cb9d198b4bbf1f1`:

- Cooling pause/evidence semantics;
- durable Cooling handling;
- recovery-budget behavior aligned with session-wide contract;
- Mix maxima 20/24/10h;
- coarse >1%C auto-HV veto removed.

## Older historical baseline

### 2026-05-02

`CHARGE_STRATEGY.md` был введён как отдельный strategy reference, чтобы не восстанавливать FSM из памяти.

На тот момент были отдельно зафиксированы:

- stage chain;
- Ca/Ca/EFB/AGM/Custom rules;
- `temp_ext` vs `temp_int`;
- Mix/Desulfation/SAFE_WAIT semantics;
- hardware vs battery safety boundary.

### Подтверждённые старые V1 contracts

- global current ceiling: 12.0 A;
- normal OVP/OCP convention: target +0.1;
- temperature compensation only from `temp_ext`, voltage only, reference 25°C;
- AGM plateau wait longer than Ca/EFB;
- SAFE_WAIT post-charge relaxation evidence;
- Ca/EFB Main hard-timeout may transition to Mix;
- V1 bank-fault risk detector is heuristic/advisory;
- dashboard intended to remain one working/updatable message;
- `/help` must not be routed to LLM/DeepSeek.

For exact V1 semantics use `V1_BEHAVIORAL_AUDIT.md`, not this historical summary.
