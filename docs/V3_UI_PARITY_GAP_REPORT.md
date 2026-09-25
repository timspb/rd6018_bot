# V3 UI parity gap report

Источник требований — V1 HMI information model в `operator_hmi.py` и связанные
compatibility panels. Rendering и handlers не изменялись.

## MATCH

- stage/program;
- voltage/current/temperature/Ah;
- output state;
- diagnostic authority/reasons;
- journal tail и однострочные события.

## ADDED TO V3

- explicit CC/CV phase;
- stage/total elapsed time;
- target V/I и active OVP/OCP limits;
- recipe/chemistry;
- waiting condition;
- transition evidence Vmax/Imin/delta/hold;
- recovery attempt/budget/result;
- SAFE_WAIT next step и DONE result.

## INTENTIONAL DIFFERENCE

V3 хранит structured evidence и journal data, тогда как V1 часто рендерит
готовую строку. Это не behavioral mismatch.

## STILL SEPARATE

V1 visual layout, Telegram callbacks, message replacement и точное legacy
wording остаются отдельным этапом. Production UI не менялся.
