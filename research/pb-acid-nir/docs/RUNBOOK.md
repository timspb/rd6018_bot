# RUNBOOK v1.0
1. Восстановить контекст по AGENTS, канону, roadmap, checkpoint и последнему отчету. Проверить реальные файлы. Работать только в корне Pb-Research.
2. Выбрать очередную тему по ROADMAP; формулировать исследовательский вопрос и критерии проверки. Поиск: первичная публикация, DOI, нормативная редакция, заводская инструкция конкретной модели; форумные протоколы как отдельный тип свидетельства.
3. Сохранять легально доступные оригиналы в sources/; не обозначать файл скачанным без проверки существования и содержимого. Фиксировать автора, дату, URL, страницы, условия, статус доступа, дату обращения. Если доступна только аннотация, явно указать это.
4. Извлекать исходные измерения, единицы, методику, контрольные группы, статистику и ограничения. Проверять арифметику. Отдельно фиксировать отрицательные результаты. Не подменять измерения интерпретацией.
5. Сопоставлять выводы с физикой, химией, электрохимией и независимыми данными. Не переносить результаты между конструкциями без обоснования. Разногласия регистрировать как гипотезы.
6. Записать отчет, обновить 01_SOURCES, HYPOTHESES, CONCLUSIONS, ROADMAP, CURRENT_CHECKPOINT, CHANGELOG; DECISIONS — только при новом решении. Не дублировать полные отчеты в реестрах.
7. Критерий литературного закрытия этапа: ключевые первоисточники проверены, условия и ограничения извлечены, выводы и нерешенные вопросы зарегистрированы. Экспериментальное подтверждение — отдельный статус. Недоступные источники не блокируют остальные темы.
8. Физические эксперименты только по утвержденному протоколу, после метрологической проверки и в пределах спецификаций батареи и оборудования. Не менять RD6018. При переходе к реализации — полный dry-run на эмуляторе до деплоя.
9. При передаче в другой чат указать корень, текущий этап и checkpoint; не начинать исследования заново. Не создавать искусственных блокеров или дублирующих документов.

## Приоритет научных исследований над реализацией (уточнение владельца 28.11.2026)
Исследования проводятся в интересах RD6018 и последующего БВ-600, но независимо от их текущей реализации, алгоритмов и аппаратных ограничений. Научная достоверность, беспристрастность и полнота исследования первичны. Существующий алгоритм не является доказательством или критерием истинности. Не ограничивать предмет исследования возможностями стенда: при недостаточной измеримости формулировать метрологические требования. Различать научный вывод, экспериментальную гипотезу, применимость к оборудованию и решение о внедрении. При противоречии реализации подтвержденным данным пересматривать реализацию, а не подгонять выводы. Изменения RD6018 и интеграция БВ-600 — отдельный этап по решению владельца.

Передача рекомендации: ID, проверенный источник или физическое доказательство, область применимости, обнаруженное либо подлежащее проверке расхождение реализации, критерий приемки, статус передачи. Непроверенные гипотезы оставлять в исследованиях. Не считать рекомендацию доставленной без подтверждения инструмента.

## Двунаправленная проверка источников — D09
Для каждой находки фиксировать: TG/source ID и авторский текст/измерения, дату, модель и химию АКБ, историю заряда/разряда, U/I/T/SG(t), приборы и погрешность, ссылку на первичную научную работу (если найдена), сопоставимость условий, альтернативные объяснения, отрицательные результаты, статус доказанности, план независимого опыта и критерии фальсификации. Не засчитывать сообщения пользователя, повторяющие наши ответы, как независимое подтверждение. Ссылки на исследование и Telegram не доказывают друг друга, пока не проверены методики и численные результаты.

## Операторский ранбук и переход между чатами (обновлено 28.11.2026)
Полный воспроизводимый порядок работы с HOME-PC MCP, Python, PDF, Telegram, проверками, кодировками, ошибками и статусами доказательности: OPERATOR_METHODS.md. Краткая актуальная точка возобновления без перечитывания истории целиком: HANDOFF_NEW_CHAT.md. При каждом исследовательском этапе (1) завершить и проверить Rxx отчет, (2) обновить источники/выводы/гипотезы/дорожную карту, (3) дописать CURRENT_CHECKPOINT и CHANGELOG, (4) ПЕРЕЗАПИСАТЬ HANDOFF_NEW_CHAT актуальными следующим этапом, блокерами, путями и проверенными командами; (5) перечитать изменённое. Текущий этап определяется по HANDOFF_NEW_CHAT.md и ROADMAP.md: ранбук не фиксирует номер этапа. В AGENTS убрано устаревшее указание «следующий R02».
Резервное копирование: корень <RESEARCH_ROOT> пока не является Git-репозиторием (.git отсутствует), поэтому локальное сохранение ≠ автоматическая синхронизация GitHub; ручной публичный снимок НИР опубликован в ветке research/pb-acid-nir коммитом 4b0a9e5, но последующие изменения нужно экспортировать отдельно. Не выполнять git init/push и не передавать секретные Telegram данные без отдельного решения владельца. Показатели из форумов и публикаций отдельно проверять по D09, отрицательные результаты сохранять.

Контрольная команда после обновления документации: python.exe <RESEARCH_ROOT>\tools\validate_handoff.py; требуемый результат HANDOFF_CONSISTENCY_PASS. Проверка read-only, секреты не читает; не заменяет Telegram API smoke test и удалённое резервное копирование.

## R20-A06–A08 original data workflow
Original publisher supplement ZIP in sources/R20, immutable hash in report 29. Offline scripts r20_eis_raw_audit.py, r20_eis_zhit_audit.py, r20_eis_capacity_candidates.py, r20_eis_capacity_join.py, r20_eis_multifeature.py. Reproduce in that order. Author numerical zHit threshold, unit and mask reconciliation still open; independent MAT decoder unavailable. Report 31 is current. Keep original data outside GitHub export.

## R20-A09
Run r20_rest_history_audit.py after A08. Extract strictly pre-discharge rest windows; preserve rejected/invalid cases and compare identical denominators. Do not treat selection-dependent model improvement as external validation.

## R20-A10
Run r20_coverage_audit.py after A09; independent dataset acquisition r20_a10_external_acquire.py; schema r20_opzs_schema_audit.py, metadata r20_bboxx_metadata_audit.py. Keep licensed original files local; preserve source test identity and timestamps. Do not treat repair labels or derived SOC as capacity reference.

## Длительные спринты (решение владельца 28.11.2026)
RESEARCH_ACCEPTANCE.md определяет S1–S5 и 88 критериев. Продолжать связанные подзадачи до содержательного checkpoint без запроса подтверждения на каждый шаг, фиксировать отрицательные результаты и недоступные источники, не повышать gate без свидетельства. Проверять матрицу скриптом validate_research_acceptance.py. A11 run r20_opzs_test_alignment.py; no physical capacity claims.

S1 block2: tools/s1_charge_evidence_math.py and tools/s1_transfer_math.py reproduce published table arithmetic only. Distinguish bulk SG from pore transport and gas from useful charge. Update acceptance gates only when criteria evidence is present.

S1 block3: tools/s1_stratification_audit.py downloads public originals and checks table arithmetic; report37. R09-K documentary distinction accepted, full protocol and water measurements still open. Preserve explicit separation of measured and inferred quantities.

S1 block4: tools/s1_completion_uncertainty.py public source archive and synthetic arithmetic. Read report38 for limits. S2 after S1 deliverable, carry unresolved criteria forward; no hardware or deployment.

S2 block1: tools/s2_pulse_comparison.py reproduces Table1/3 descriptive arithmetic and public archive. Distinguish measured gas and estimated input Ah, historical FAT and matched control, predicted life and observed EOL. Read report39.

S2 block2: tools/s2_retention_audit.py archives primary reports and computes descriptive changes; report40. Distinguish scheduled cycle cap, actual failure, shallow cycle count and measured throughput EFC; recovery yield denominator must be known.
