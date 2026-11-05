# RD6018 Control dashboard

The versioned source is [`rd6018_control.yaml`](rd6018_control.yaml). It uses
Home Assistant Sections layout and stock cards only. The dashboard is a
read-only display: it contains no `switch` or `number` control entities and no
service actions. Tile taps open More Info.

## Live installation

- Home Assistant: `http://192.168.1.102:8123/rd6018-control`
- Dashboard title: `RD6018 Control`
- URL path: `rd6018-control`
- Installed through the authenticated Home Assistant WebSocket dashboard API.
- The existing `dashboard-rd6018` dashboard was read before installation and
  left intact.
- The dashboard uses only built-in frontend cards; no frontend resource or
  HACS dependency is required.

To compare or restore the dashboard configuration, open the YAML file and use
the dashboard raw configuration editor. If recreating it, first add a new
dashboard with URL path `rd6018-control`, then paste the YAML configuration.
Do not overwrite `dashboard-rd6018`.

## Entity mapping and interpretation

Live HA state metadata on 2026-11-05 confirmed the entity IDs used here.
Measured battery voltage is `sensor.rd_6018_battery_voltage`; measured output
current is `sensor.rd_6018_output_current`. The similarly named
`number.rd_6018_output_current` is a writable setpoint and is deliberately not
used. Setpoint/protection tiles use the separate readback sensors:

- Vset / Iset: `sensor.rd6018_rd_6018_set_voltage_readback_v2` and
  `sensor.rd6018_rd_6018_set_current_readback_v2`.
- OVP / OCP: `sensor.rd6018_rd_6018_ovp_readback_v2` and
  `sensor.rd6018_rd_6018_ocp_readback_v2`.
- CV / CC: `binary_sensor.rd_6018_constant_voltage` and
  `binary_sensor.rd_6018_constant_current`.
- Output is shown as the read-only numeric register mirror
  `sensor.rd6018_rd_6018_output_state_code_v2`, never as the output switch.
- Protection code and lease, quarantine, autonomous and communication-age
  values are informational HA entities.

The history graph shows Recorder history for measured battery voltage and
measured output current over 24 hours. HA is a secondary display path. Its
states, history and this dashboard are not direct ESP Native API evidence and
must not be used to claim physical Output status or authorize charging,
ownership, deployment or safety decisions. Before any such check, follow
[`ESP_NATIVE_LIVE_EVIDENCE.md`](../../ESP_NATIVE_LIVE_EVIDENCE.md) and obtain
fresh typed callbacks directly from the ESP.

## Verification record

HA version reported `2026.10.4`. The `/api/config`, `/api/states`, dashboard
list, existing RD6018 dashboard config, frontend resources and 24-hour
Recorder history were queried read-only. Stock frontend resources were
available; the live RD6018 dashboard used Sections layout. The new dashboard
was saved and read back through the dashboard WebSocket API. No physical
output, setpoint, lease, battery, service or firmware command was sent.

Direct ESP Native API access was blocked during this task because the existing
local ESPHome encryption key was unavailable. HA showed Output ON at the time
of inspection; this is only a secondary HA observation, not physical
verification. No output operation was attempted.

## Компактная ревизия v2 по проверке на экране — 2026-11-05

По фактическим скриншотам устранены три UX-дефекта: узкая колонка (`max_columns: 1`), вывод сырого `output_state_code_v2=1.0` вместо человеческого состояния выхода, графики разных единиц в тесной общей карточке. Теперь Sections `max_columns: 2`, две независимые области для показаний/параметров и графиков/безопасности, раздельные 24-часовые графики В и А. Крупные измерения и статус выхода/режима/защиты представлены через **уже установленный** `custom:button-card`, исключительно как read-only (`more-info`, без toggle/сервисных вызовов). Статусы имеют явные unknown/unavailable. Убраны бинарные OVP/OCP-дубликаты и большая часть длинного списка диагностических сущностей с основной области. Подтверждено WebSocket HA: `lovelace/config/save` + readback точное совпадение, `sections=2`, `max_columns=2`, старая `dashboard-rd6018` не затронута. Показания HA не заменяют прямую аппаратную проверку ESP. Проверка реального рендера на устройствах пользователя ещё необходима.

## v3 — операторская компоновка по скриншоту, 2026-11-05

По просьбе оператора убраны избыточные heading и разреженные строки слева. Верхние измерения: АКБ U и фактический I; ниже три компактные карточки на одной строке: выход (сырой readback 1.0/0.0 преобразуется в «Включён»/«Выключен», ON подсвечен светло-зелёным), CV/CC, внешний температурный датчик `sensor.rd_6018_temperature_external` (температура АКБ только при правильной установке датчика на батарее). Третья строка — два read-only readback-параметра Vset/Iset, без прямого управления RD6018. Убраны самостоятельные блоки «Уставки и ограничения» и «Защита»; OVP/OCP и сырые диагностические коды исключены из основного вида. Диагностика lease/Modbus помещена в сворачиваемый `custom:fold-entity-row` — плагин уже был установлен в HA102, ничего нового не установлено. Правая колонка сохраняет два отдельных 24-часовых графика U/I. API-приёмка: WebSocket save + exact readback PASS, старая панель сохранена, все проверенные entity_id существуют, команд записи в устройство не было. Визуальная приёмка после обновления страницы остаётся за оператором.
