# RD6018 Operator Charge Card Refinement v2

Статус: **OPERATOR_CHARGE_CARD_REFINED**

Карточка строится по границе:

`OperatorStateSnapshot → ChargeCardViewModel → Telegram formatter`.

Новая presentation-модель выдаёт ровно пять непустых строк:

```text
🔋 battery · phase  mode
⚡ voltage V  current A  CC/CV
🎯 target/condition
🔋 Ah  t=elapsed
MIN=value [MAX=value] Hold=timer
```

Удалены из карточки RD6018, слово «ЗАРЯД», температура БП и служебные коды.
Diagnostics не входит в `ChargeCardViewModel` и остаётся отдельным dashboard
пунктом.

MAIN показывает зарегистрированный минимум и hold timer; MIX — MIN/MAX,
условие и timer; HOLD — condition и timer; SAFE_WAIT — причину ожидания.
Отсутствующие значения отображаются как `UNKNOWN`.

Изменён только Telegram presentation adapter. V2 runtime, V3 domain,
ChargeEngine, PhaseLifecycle, Safety, Execution и node 101 не затрагивались.
