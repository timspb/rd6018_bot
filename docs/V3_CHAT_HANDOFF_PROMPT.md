# V3 chat handoff prompt

Ты продолжаешь работу над `timspb/rd6018_bot` в ветке
`codex/v3-runtime-consolidation`.

Сначала прочитай:

1. `docs/V3_PROJECT_RUNBOOK.md`;
2. `docs/V3_BENCH_VALIDATION_PROTOCOL.md`;
3. `docs/V3_OUTPUT_STATE_TRANSITION_EVIDENCE_2026-09-14.md`;
4. `AGENTS.md`.

Не переизобретай архитектуру и не начинай работу с просмотра всей истории
чатов. Текущий документированный HEAD:
`022e01ff9eb2c9421b0e5c39b81c298eff396463`.

Правила:

- бот — UI/операторский адаптер, не владелец зарядки и железа;
- решения принимает V3 runtime charge strategy;
- telemetry evidence, diagnostics, safety и execution — разные границы;
- любой physical write проходит Safety → Envelope → manual bench lease → ARM
  → connector → fresh readback → evidence;
- HAESPConnector и ESPDirectConnector независимы; автоматический fallback
  запрещён;
- перед выбором Vset сначала прочитать напряжение АКБ, затем вычислить Vset из
  config. Нельзя ставить фиксированное напряжение ниже АКБ;
- после подтверждения ON держать выход заданное config время (сейчас 10 с),
  затем отключить;
- финальный OFF считается подтверждённым только при `Output OFF` и `current 0
  A`, с ожиданием задержанного readback;
- секреты не выводить и не коммитить;
- V1 UI не удалять: его внешний вид и информационная модель разбираются
  отдельно;
- не менять production runtime, ESPHome, firmware, node 101 или V2 safety
  wrappers без отдельного явного задания.

Текущий physical evidence:

- battery около `13.13–13.15 В`;
- bench target выбирается как battery voltage плюс margin из
  `config/physical/bench.yaml`;
- короткий HA-ESP-RD `OFF → ON → OFF` выполнен;
- ON readback: `1.526 с`;
- OFF readback: `2.546 с`;
- zero-current readback: примерно через `5 с` после первоначального OFF;
- полный независимый ESP-direct transition run ещё не закрыт.

Ближайшая задача: продолжать только с актуальным evidence, сначала делать
read-only preflight, не повторять физический запуск при неизвестном состоянии и
после каждого изменения обновлять соответствующий runbook/evidence документ.

Если обнаружен новый дефект, сначала зафиксируй symptom, root cause, impact и
план исправления. Не маскируй mismatch и не объявляй PASS без свежего
readback/evidence.
