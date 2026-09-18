# V3 UI и Charge Journal

```text
Runtime domain -> ChargeJournal / RuntimeUISnapshot -> любой UI consumer
```

`ChargeJournalEntry` хранит одну семантическую запись. `format_entry()` выдаёт
ровно одну компактную строку; engine не занимается языком или оформлением.
Периодические записи и события создаются через `JournalEventFactory`, а
transport-independent recorder пока имеет только in-memory реализацию.

`RuntimeUISnapshot` состоит из независимых `ChargeView`, `TelemetryView`,
`DiagnosticsView`, `SafetyView`, battery/output data и journal tail. UI-модели не
импортируют FSM, controller, RD, Output или legacy globals и не могут создавать
ChargeIntent.

Test-only `tests/ui_mapping_fixtures.py` принимает заранее подготовленный
display mapping для shadow-сравнения с V1. Telegram handlers, callbacks и каноническое
V1-оформление не переносились и будут разобраны отдельным этапом.
