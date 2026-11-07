"""Operator action labels and existing callback destinations; presentation only."""

from application.operator_actions import OperatorAction
from runtime.ui.telegram.analysis import ANALYSIS_CALLBACK_DATA
from runtime.ui.telegram.charge import BATTERIES_CALLBACK_DATA, CHARGE_CALLBACK_DATA
from runtime.ui.telegram.details import DETAILS_CALLBACK_DATA

OPERATOR_ACTION_LABELS = {
        OperatorAction.START_CHARGE: ("⚡ Режимы заряда", CHARGE_CALLBACK_DATA),
        OperatorAction.SELECT_PROFILE: ("🔋 АКБ", BATTERIES_CALLBACK_DATA),
        # Newly rendered panels must use the managed confirmation-based route.
        OperatorAction.STOP_CHARGE: ("🛑 Стоп", "operator_managed_stop"),
        OperatorAction.PAUSE_CHARGE: ("⏸ Пауза", "operator_pause_toggle"),
        OperatorAction.RESUME_CHARGE: ("▶️ Продолжить", "operator_pause_toggle"),
        OperatorAction.SHOW_LOG: ("📋 События", "logs"),
        OperatorAction.SHOW_DIAGNOSTICS: ("ℹ Подробнее", DETAILS_CALLBACK_DATA),
        OperatorAction.ACK: ("✅ Подтвердить", DETAILS_CALLBACK_DATA),
        OperatorAction.ADOPT_MIX: ("🧲 Подхватить Mix", "rd_live_mix"),
        OperatorAction.STOP_MIX: ("⏹ Остановить Mix", "operator_adopted_stop"),
        OperatorAction.DISABLE_OUTPUT: ("⏹ Output OFF", "rd_hands_off_output_off"),
        OperatorAction.REAUTHORIZE_MANUAL: ("▶ Авторизовать", "v2_manual_reauthorize"),
        OperatorAction.DISCARD_MANUAL: ("🗑 Отказаться", "v2_manual_discard"),
        OperatorAction.RETURN_PB_CONTROL: ("🔒 Вернуть Pb-контроль", "rd_hands_off_disable"),
    }
