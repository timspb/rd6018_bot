# RD6018 — стерильное хранение HOME-PC, проход 2026-11-05

## Канон (без исключений для рабочих данных)

**Единственное место хранения рабочих файлов RD6018 на HOME-PC — `E:\CODEX\rd6018_bot`.** Исходники и ранбуки — в Git; локальные аппаратные ресурсы и секреты — только внутри того же каталога в игнорируемых Git подпапках; временные задачи после использования удаляются. В корне других дисков, Downloads, Windows Temp, WSL /tmp, внешних Git-клонах и старых IDE-профилях не должно оставаться самостоятельных RD6018 артефактов. Не создавать backup/архивов «на всякий случай». Не смешивать RD6018 с PCP/Wake Bridge/другими проектами.

## Исполнено и проверено

1. `D:\Users\HOME-PC\Downloads`: 12 RD6018/Riden/RDFlasher файлов и каталогов перенесены в `local_assets/vendor`; поиск по именам перенесённых корневых объектов — 0. Внутри vendor удалены 25 устаревших архивов, инсталляторов и дубликатов, 295997649 байт. Оставлены 398 файлов, 62644966 байт: RDFlasher, CH341 driver, flash_download_tool 3.9.7, RidenPowerSupply 1.0.0.17, riden-dongle 1.2.0, оригинальные прошивки и справочник; отдельные ранние YAML/controller/firmware-файлы перенесены в тот же каталог. Это локальные аппаратные ресурсы, не Git-исходники. `local_assets/` добавлен в `.gitignore`.
2. `RD6018-CI`: выделенный GitHub Actions runner с systemd unit `actions.runner.timspb-rd6018_bot.rd6018-wsl2-01.service`; метки обязательной owner-triggered проверки `rd6018-ci`, `rd6018-wsl2`. Удалены непригодные для работы старые local-acceptance окружения (~922 MiB), временный runner update (~683 MiB), старый checkout (~16 MiB), прежние bin/externals версии 2.338.0 (~683 MiB). После удаления unit был ACTIVE; `/var/lib/rd6018-actions-runner` ~1.6G, `/opt/rd6018-actions-runner` ~685M, test venv ~290M. Оставлены действующий runner 2.338.2 и Python tools, нужные матрице CI.
3. Windows `.codex/memories` и `memories_v2`: удалены 5 RD6018 rollout summaries; из Windows Recent удалены 8 RD6018 ссылок; из Start Menu удалены 2 ссылки/каталога RD6018-CI. Исполнение runner от ярлыков не зависит.
4. Git `main` исходно синхронизирован с GitHub на `9f5deed3825bbb016c75e7af8f3937630559d18e`. Новые .gitignore/документационные изменения пока требуют отдельного нормального fast-forward push.

## Оставшаяся операция: размещение WSL VHDX внутри канона

Фактический WSL `RD6018-CI` зарегистрирован в `C:\Users\HOME-PC\AppData\Local\wsl\{dcae8272-0ae5-458d-9a8e-ffad895cbb07}`, виртуальный диск `ext4.vhdx` был ~10.48 ГБ до чистки. Это **единственный подтверждённый крупный RD6018 рабочий storage вне канонического пути**. Внутренние Linux `/opt/rd6018-actions-runner`, `/var/lib/rd6018-actions-runner`, `/opt/rd6018-ci-test-venv` должны остаться по тем же Linux путям, но физический VHDX должен переместиться в `E:\CODEX\rd6018_bot\infrastructure\wsl\RD6018-CI`; эта подпапка исключена из Git.

Штатная попытка:
- проверено, что `Runner.Worker` не выполнял задание, только Listener;
- `wsl --terminate RD6018-CI` завершился 0;
- `wsl --manage RD6018-CI --move <canonical_path>` завершился `WSL/Service/MoveDistro/ERROR_SHARING_VIOLATION` — VHDX занят;
- Registry `BasePath` **не изменился**. Исходный дистрибутив не удалён; runner повторно запущен и проверен ACTIVE. Пустой целевой каталог удалён.

**План cutover без второго runner и потери CI**: (1) дождаться отсутствия `Runner.Worker` и текущих задач в остальных WSL; (2) временно остановить только задачи, совместимые с полной остановкой WSL — не прерывать PCP/Codex/Wake Bridge; (3) в согласованное безопасное окно выполнить `wsl --shutdown` (глобальная операция, сейчас не допускается из-за активного Ubuntu-24.04), затем штатное `wsl --manage RD6018-CI --move E:\CODEX\rd6018_bot\infrastructure\wsl\RD6018-CI`; (4) подтвердить новый WSL Registry BasePath, единственный физический VHDX внутри канона и отсутствие старого VHDX; (5) запустить существующий `RD6018-CI`, подтвердить systemd unit ACTIVE, ровно один Listener, GitHub runner online/idle с прежними метками и owner-triggered trusted acceptance; (6) убрать только остатки неудавшегося переноса и проверить, что Git/CI/другие WSL остались работоспособными. Не `wsl --unregister`, не создавать новый runner, не менять GitHub runner registration/token, не перемещать /opt в drvfs без сохранения POSIX semantics.

## Критерии завершения

- **Files**: независимый поиск на Windows C:/D:/E: и в обеих WSL не находит рабочих RD6018 объектов вне `E:\CODEX\rd6018_bot`, кроме системных записей, необходимых WSL/Windows для работы самого дистрибутива. Непроверенные и недоступные Windows protected paths отметить отдельно.
- **Runtime**: CI runner ACTIVE/online и owner-triggered workflow работает штатно; заряд/node104/ESPHome не затронуты.
- **Git**: `git status --porcelain` пуст, `origin/main == main` по точному SHA; vendor binaries/секреты/VHDX не опубликованы.
- **Disk**: реальный VHDX перемещён и старое место пусто; занятое место измерено после операции. Уменьшение размера VHDX требует отдельной offline compact проверки, не путать с `du` внутри WSL.

**Текущий статус: частичная санитаризация PASS; строгая стерильность HOME-PC NOT YET ESTABLISHED, пока физический VHDX RD6018-CI остаётся на C: и не завершён повторный тотальный поиск по защищённым Windows путям.**
