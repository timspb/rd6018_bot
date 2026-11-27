# HANDOFF_NEW_CHAT — Pb-Research
Дата обновления: 2026-11-28.
NEXT_STAGE: R20
CURRENT_REPORT: 22_R19_RECOVERY_DURABILITY.md
Не начинать повторно R01–R19; использовать их отчёты, источники и ledgers.

## Среда и обязательный порядок
Рабочий корень HOME-PC: <RESEARCH_ROOT>. В ChatGPT инструменты HOME-PC доступны через functions.exec → ALL_TOOLS → tools.mcp__mcp_gateway_home_pc__read_file/write_file/edit_block/exec_structured. Сверять точные tool schemas через ALL_TOOLS, не объявлять инструменты недоступными без проверки.
Чтение: AGENTS.md → 00_CANON.md → HANDOFF_NEW_CHAT.md → RUNBOOK.md → OPERATOR_METHODS.md → ROADMAP.md → CURRENT_CHECKPOINT.md → последний отчёт. Проверять текущий stage по HANDOFF + ROADMAP + верхнему блоку CURRENT_CHECKPOINT; ниже в checkpoint остаётся исторический журнал.
D07/D09: научное исследование независимо от RD6018/БВ-600. Разделять peer-reviewed full text, author copy, abstract, patent, forum anecdote; сохранять negative evidence и discrepancy; не выдавать аннотацию за полный текст. Не придумывать методики/уставки из отдельных статей.

## Текущий статус и результат R19
R19 PARTIAL; отчёт 22_R19_RECOVERY_DURABILITY.md. Найдены два 40-cycle follow-up:
- Karami et al. 2009 inverse charge: 40 циклов, авторы пишут ≥80% cycle endurance vs fresh, но metric/n/EOL не определены. Это не multi-year service life. R18 report corrected by erratum.
- Lee et al. 2023 high-voltage restoration: 40 циклов recovered 2V cells, average 91.3% rated/98.6% new, cycle 40 = 89% rated; SEM показывает снижение porosity и рост PbSO4 после цикла. Не переносить на automotive 12V/Ca-Ca.
Временной ряд Ohajianya 2021 (4 Gel batteries, PV+desulfator, no control) немонотонный: на 10 неделе две батареи ниже baseline. Shi/Ferone/Rahn 2012/2013: одна sulfated cell +41% после 313h, финал 56.3/88Ah, 3 другие cells dehydrated; последующие life tests отсутствуют. PNNL 2022 aging benchmark (не recovery): 4 AGM lead-carbon modules, 18–28 months, 289–728 EFC, periodic capacity and pulse-R. IEC 60095-1:2018 corrected 2026-02 — starter-battery framework.
R19 conclusion: короткий циклический эффект наблюдался, но независимого matched multi-month/multi-year inverse-charge recovery test на современных automotive Ca/Ca/EFB/AGM не найдено.
tools/r19_durability_analysis.py — arithmetic/provenance PASS; source PDFs: sources/R19/Shamim_Viswanathan_2022_Energies_3389_PNNL.pdf, Shi_Ferone_Rahn_2012_Pressure_Feedback.pdf, IEC_60095-1_2018_Corrected_2026_Preview.pdf. SHA256 в 22_R19_RECOVERY_DURABILITY.md. Lee2023 PDF локально HTTP403, но full web text прочитан; Ohajianya2021 full HTML mirror прочитан.
Local Telegram: только 1800 recent messages из примерно 92940, no controlled long-term recovery case. Не запрашивать всю историю без отдельной необходимости. TG-02, posts 105969/105681/105299 в TELEGRAM_TRIAGE_001.md.
R00 DONE; R01–R19 PARTIAL (R04-D also PARTIAL); R20 OPEN.

## Next stage R20
Синтезировать C01–C91 и H01–H59 по уровням доказательности, химии/конструкции и области применимости. Сформировать decision matrix «что можно утверждать / что неизвестно / что запрещено выводить», no-go boundaries и требования к будущей метрологии. Не превращать R20 в зарядной рецепт или план физического воздействия. Проверить противоречия между R01–R19 и закрыть их корректно, не удаляя negative evidence.

## GitHub NIR
Репозиторий timspb/rd6018_bot, ветка research/pb-acid-nir, только каталог research/pb-acid-nir/. Последний опубликованный SHA до R19: 08474c3b1255bbbfc6426065928eb9d4e079cceb (проверить актуальный tip перед правкой). Локальный <RESEARCH_ROOT> не имеет .git; auto sync отсутствует. Публичный экспорт: tools/prepare_github_nir.py; аудит: tools/verify_public_export.py; проверка handoff: tools/validate_handoff.py. Публиковать только vetted docs/tools в NIR branch, проверить compare main и что ни один путь вне research/pb-acid-nir не изменён.
Исключить из публичного экспорта: сторонние PDF, Telegram raw/cache/media, private/, .env.secrets, session/QR, local venv, private case data. Не менять main, RD6018 code, ESP, node104, HA или БВ-600.
