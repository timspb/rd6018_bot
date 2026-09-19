# RD6018 Deployment Access Recovery — WORKSTREAM 39

## Result

**`ACCESS_READY`** — штатный read-only доступ к node 101 и Home Assistant 102
восстановлен через сохранённые WinSCP-сессии; ESPHome 1.28 подтверждён по
Native API.

## Access inventory

| Mechanism | Status | Finding |
|---|---|---|
| SSH config | PARTIAL | config exists, but no node-101 host entry with usable auth was found |
| known_hosts | PRESENT | node 101 fingerprint is known locally |
| SSH agent | MISSING | `SSH_AUTH_SOCK` and `SSH_AGENT_PID` absent |
| local SSH key | PRESENT | configured key file exists; authentication to 101 failed |
| WinSCP storage | PRESENT | session targeting `192.168.1.101` exists |
| WinSCP executable | PRESENT | `WinSCP.com` найден в штатной установке |
| deployment service environment | REACHED | `/root/rd6018_bot/.env` доступен read-only |
| HA service environment | REACHED | `/homeassistant/esphome/secrets.yaml` доступен read-only |

Сохранённые WinSCP-сессии использованы для read-only подключения. Пароли,
ключи и токены не выводились и не сохранялись в репозитории. Временные копии
секретных файлов удалены после presence-only проверки.

## Verified access and live read-only checks

* node 101: `rd6018-bot.service` is `active`; deployed HEAD `10af870`;
  `/root/rd6018_bot/.env` contains `HA_TOKEN`.
* node 102: Home Assistant API returned successfully; 220 states were read,
  including 57 RD6018-related entities.
* ESPHome `192.168.1.28:6053`: Native API authenticated with the configured
  `rd6018_api_encryption_key`; device info and 66 entities were read; no
  services were called.
* Current read-only snapshot: RD output `ON`, approximately `17.11 V / 3.49 A /
  59.74 W`, internal temperature `44 °C`, external `36 °C`, CC active,
  protection code `0`, lease armed with roughly `11 minutes` remaining at the
  observation point. These values are time-sensitive.
* The deployed service tree has a pre-existing modification in
  `config/charge/manual.yaml`; it was not changed.

## Next step

Access recovery is complete. Repeat Workstream 38 from the штатное service
environment using the existing observer composition. The ESP credential is
stored under the ESPHome secret name `rd6018_api_encryption_key`, not the
generic environment name `ESPHOME_API_KEY`.

No secret values belong in this report or repository.
