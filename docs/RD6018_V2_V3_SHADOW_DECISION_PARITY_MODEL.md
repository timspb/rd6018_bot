# RD6018 V2/V3 Shadow Decision Parity Model

Статус: **V2_V3_SHADOW_PARITY_READY**

## Input boundary

`ShadowDecisionInput` содержит только read-only context:

- synthetic or supplied telemetry;
- battery/profile;
- current phase and program;
- lifecycle state;
- session/timestamp correlation.

V2 и V3 представлены независимыми immutable `ShadowDecisionView`. Ни один
view не является владельцем другого.

## Comparison

Сравниваются:

- selected program;
- phase;
- voltage/current targets;
- safety result;
- execution intent fields.

Результаты:

- `MATCH` — все поля равны при доступной telemetry;
- `EXPECTED_DIFFERENCE` — все расхождения явно объявлены как expected;
- `DIVERGENCE` — необъявленное расхождение;
- `UNKNOWN` — telemetry отсутствует или неактуальна.

Каждый `ShadowDivergence` содержит timestamp, session, reason, source owner,
field и оба значения. Расхождения не исправляются автоматически.

## Observe-only guarantee

Parity engine не вызывает V2/V3, не изменяет state, не создаёт commands,
lease operations или physical requests. Execution intent сравнивается как
данные; результат остаётся report-only.

## Verification

Добавлено 6 focused tests:

- identical decision;
- different program;
- expected phase difference;
- safety divergence;
- missing data;
- forbidden physical/influence dependencies.

Node 101, deployment, START/STOP, ownership transfer и physical execution не
подключались.
