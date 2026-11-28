# S5 D09 intake — Telegram four-source read-only and longitudinal observations
2026-11-29. User expressly requires strict read-only Telegram. No joining/leaving, posting/editing/deleting, reactions, read acknowledgements, status changes, new authentication or account operations. Existing authorized session only. Connector local v0.2.0 four explicit names, source parameter validated before network access, explicit connect/disconnect and authorization check, receive_updates=False. No write RPC added; local file writes only. Scope is application allowlist, not a new server-side restriction of whole Telegram account.
## Access and acquisition
Executed telegram_connector/test_four_sources_readonly.py: MCP lists exactly four existing read methods, rejects unlisted source on all four. Recent: UklonGroup 40 (68763–68805), zaryd10 40 (460353–460394), beregok7 40 (315423–315520), zaryadAKBin 2 (106233–106234). All PASS, exit0. Search 20 hits each UklonGroup "циклирование"/"циклов", zaryd10/beregok7 "циклов"; two specific series searches "Аком Стандарт"/"Тюмень АГМ" each60 hits, root-replies50/54. Root messages 45555/24823 had no text. Total313 distinct (source,id) across ten JSONL files, excluding roots, not full history. No media downloaded or inspected this pass. Some hits unrelated sodium/lithium; excluded. No raw cache, private identifiers, media or session exported. Local audit tools/s5_telegram_cycling_audit.py executed PASS; cache hashes printed, raw remains local. 
## TG09 Akom Standard observational series
19 selected discharge observations, same reply thread45555; messages reported by participant, not independently instrument-calibrated. Values in Ah, positive magnitude of discharge, author-normalized Q25 separate. Dates refer to posting, not always measurement.
| Cycle | Message ID | Q | Q25 |
|---:|---:|---:|---:|
|6|46026|52.822|—|
|7|46076|52.648|52.873|
|8|46274|51.878|52.511|
|9|46487|49.562|50.432|
|10|46700|51.667|53.005|
|11|46818|49.722|49.982|
|12|46897|44.104|44.785|
|13|47008|44.263|44.047|
|14|47065|43.732|42.608|
|15|47091|39.205|38.802|
|16|47347|46.260|46.402|
|17|47488|35.209|36.325|
|19|55751|38.294|—|
|20|56614|41.751|43.857|
|21|57028|42.047|44.428|
|22|57643|40.935|43.785|
|23|58676|42.804|44.709|
|24|60058|41.459|44.245|
|25|61695|42.412|43.875|
Link format https://t.me/UklonGroup/<message id>. E.g. https://t.me/UklonGroup/47347 and https://t.me/UklonGroup/61695. 3A approximate from measured Ah/time, not established standard C20; rated capacity/cutoff/T trace and correction formula not verified. Cycle6→25 raw −19.71%, not lifetime since initial missing, no verified EOL. Cycle15→16 after elapsed month and recharge +7.055Ah/+17.99%; cannot isolate rest from recharge and T. Cycle16→17 −11.051Ah/−23.89% vs prior Q, reported −31.39% uses different denominator; preserve absolute. Changing charge profiles, return Ah, mechanical rocking, ambient T, interruptions confound. 54525 says charger statistics lost; 54535 reports accidental extreme discharge during firmware incident; do not reproduce. 47460 describes incorrect settings applied with WiFi fault; 56610 counter reset during cycle20. No independent parallel control or confirmed defect label. Cross-check C99/C100/C107/C159/C180 and report48; apparent recovery after pause is consistent with conditioning/availability, no confirmation of claimed "technical sulfate" mechanism. No proof high-voltage superiority or harm from one sequential contrast.
## TG10 Tyumen AGM observational series
25 reported discharges in same reply thread24823:
| Cycle | Message ID | Q | Q25 |
|---:|---:|---:|---:|
|46|44115|35.128|35.232|
|47|44137|35.086|35.320|
|48|44248|34.668|35.209|
|49|44337|40.634|41.578|
|50|44380|37.847|37.140|
|51|44610|32.822|—|
|52|44685|29.608|29.905|
|53|44742|34.259|34.843|
|54|44809|35.295|36.177|
|55|44880|35.788|36.343|
|56|44920|38.063|38.591|
|57|45047|35.935|36.336|
|58|45190|36.482|36.786|
|59|45270|35.885|36.309|
|60|45506|36.383|36.713|
|61|45573|35.772|36.147|
|62|45644|35.668|35.680|
|63|45729|33.819|—|
|64|45831|35.674|35.936|
|65|45854|35.663|35.383|
|66|45910|34.831|34.746|
|67|45994|33.111|33.249|
|68|46091|33.823|33.957|
|69|46278|32.049|32.320|
|71|46622|29.155|29.714|
https://t.me/UklonGroup/44337 , https://t.me/UklonGroup/44360 , https://t.me/UklonGroup/44380 . Cycle46→71 raw −17.00%, not life-to-EOL. Cycle48→49 +5.966Ah/+17.21% after changed charging. Cycle50 author reports device indicated 76.6Ah input, warming and prolonged charge; next Q37.847Ah vs40.634Ah, −6.86%. This is a valuable negative observation, not independent proof that Berezhok caused irreversible damage. Different device/charge preparation, T, actual Ah unknown; 44124 reports counter reset bug during charge47. No new validated profile. Cross-check C22/C47/C100/C154–160/C184–185.
## TG11–13 candidate observations
- UklonGroup 68763/68767: recent report of counter freeze/incorrect current after interruption and resume. Data-quality warning; not evidence all older logs invalid or our RD6018 affected.
- zaryd10 460367/460394: new Akom Reactor reportedly worse tester readings after attempted charge; no independent Q, attachment not examined. C34/C150/C179, negative case retained E4. 
- beregok7 314704/315506: stable SG and uneven bank behavior discussed; no matched spatial SG(z), water balance or C20. C10/C26/C148–149; not verified completion. Other charge "cycles" refer to multi-day charge stages, not measured discharge cycles; don't combine denominators. 
D09: all new forum cases E4, T2/T4 depending on observation; no independent replication or primary Q-gate advancement. User-supplied commercial concerns about zaryd10/beregok7 treated as potential bias, not proof of misconduct. No quantitative C/H promoted. S5 remains 62/88, C192/H93. Next D09: obtain specific archived curves and earlier series from same threads, verify nominal capacity/cutoff/calibration, time alignment and distinct specimen IDs, assess comparison with Akom EFB if available. Only selective existing read methods; no full history scrape or joining. Then resume S5 protocol consolidation.