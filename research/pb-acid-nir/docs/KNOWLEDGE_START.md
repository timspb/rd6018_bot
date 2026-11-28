# Pb-Research — единая точка входа
Актуально: 29.11.2026. Канон 00_CANON.md и решения D07/D08/D09/D10 обязательны. Научная база ≠ готовый алгоритм зарядки. Чек-лист RESEARCH_ACCEPTANCE.md: D22/22, Q20/22, K19/22, P1/22; теория 61/66, весь НИР 62/88. Пять теоретических пробелов: R04-D-Q, R09-Q, R05-K, R06-K, R12-K. Протоколы P1/P2 проект report56; P3 и далее не закрыты.
## Быстрый доступ
Markdown — первичный версионируемый источник. SQLite FTS5 — производный индекс, не источник истины. Индекс строится только из корневых md (или docs/ в экспортном репозитории), без private/, sources/telegram, session, PDF и исходных логов.
- Научный вывод Cxxx: 49_S5_STATEMENT_EVIDENCE_MATRIX.md (192 записей, E/T и ограничения).
- Дополнительная запись Sxxx: KNOWLEDGE_SUPPLEMENT.md (22 записи reports51–57, не независимые новые C).
- Гипотеза Hxxx: HYPOTHESES.md (93 записи; проверять индивидуальный статус).
- Источники: 01_SOURCES.md и исходные ссылки в отчётах. Ссылки из индекса являются текстовыми указателями, а не автоматически верифицированными первоисточниками.
- Методология: EXPERIMENT_PROTOCOL.md, report56; рекомендации отдельно INTEGRATION_RD6018.md, без разрешения на внедрение.
## Поиск из любого чата с HOME-PC MCP
Вызвать exec_structured environment=windows, program=python, cwd=локальный корень проекта, args=["-X","utf8","tools/knowledge_index.py","search","хлыст","--limit","5"]. Возвращает JSON: id/category/file/first_line/last_line/statement/evidence/transfer/kind/limitation/links. Для конкретного ID использовать get S013, для состояния stats. При STALE INDEX перестроить build и повторить. Только локальное чтение при search/get/stats, build пишет исключительно производный индекс. Отдельный новый MCP endpoint не требуется для действующих чатов с HOME-PC; для чатов без него доступ не подтверждён.
На чистой копии GitHub из research/pb-acid-nir каталога: python -X utf8 tools/knowledge_index.py build. Пример search "импеданс" --category claim --limit 5. Лексический поиск с двуязычными алиасами, не семантический RAG; уточнять запрос, читать оригинал и учитывать более поздние исправления.
## Тематические маршруты
| Задача | Направления / документы |
|---|---|
| Зарядоприёмность, стратификация, MAIN/MIX | R01/R04/R08/R09; отчёты34–38,48,53 |
| Сульфатация, активные массы, коррозия, ток | R02/R03/R10/R16/R17; отчёты35,41,47,48,55 |
| Релаксация, импеданс, хлыст, SOC/SOH | R05/R06/R07/R12; отчёты29–33,43–45,54–55 |
| Ёмкость, Пейкерт, измерения | R11/R15; отчёты44,46,54,56 |
| КЗ, саморазряд, переполюсовка | R04-D/R13/R18; отчёты41,43 |
| Ресурс, сравнительная эффективность | R14/R19; отчёты39–42,51–54 |
## Обновление и ограничения
Сначала исходный отчет и его ограничения, затем C/H или дополнение S с явной ссылкой; не переприсваивать ID, исправления с указанием заменяемой интерпретации. Перестроить индекс и проверить контрольные запросы после изменения. Сведения без E/T в документном фрагменте не имеют самостоятельной доказательной оценки. Не считать количество фрагментов количеством независимых исследований. Точные версии источников и raw PDF по-прежнему в локальном архиве. Текущий этап — оптимизация базы и пять теоретических пробелов; затем P3. Исторические подробности в HANDOFF_NEW_CHAT.md и CURRENT_CHECKPOINT.md, использовать их только при необходимости, не перечитывать целиком для тематического ответа.

Report57: independent VRLA field cohort Siekierski2026; Mohsin2022 Table III error recalculation from indexed copy, macro MAE0.8524Ah/MAPE16.32%, reported abs signed bias per rated22Ah; no blind C20 or external calibration. Pilatowicz relaxation and alternative mechanical shorts reviewed; Zeng/Mamadou full evidence still unavailable. Five theoretical gates OPEN (61/66, total62/88). S019–S022 indexed. Next independent raw relaxation/capacity candidate and targeted primary sources. No device work.
