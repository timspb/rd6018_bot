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

# Existing D061 entry workflow is a presentation affordance rather than an
# OperatorAction capability: the coordinator still owns its callback workflow.
MANAGED_ADOPTION_BUTTON = ("🔒 Забрать под Pb-контроль", "rd_managed_adopt")

# RD ownership recovery controls keep their existing callback workflows.
RD_OWNERSHIP_HANDS_OFF_BUTTON = ("🔓 Режим РД — не лезь", "rd_ownership_hands_off")
RD_OWNERSHIP_RELEASE_BUTTON = ("🔓 Отпустить РД", "rd_hands_off_release_confirm")
RD_OWNERSHIP_RETURN_BUTTON = ("🔒 Вернуть контроль заряда", "rd_hands_off_disable")
RD_OWNERSHIP_ADOPT_BUTTON = ("✅ Принять управление", "rd_ownership_adopt")
RD_OWNERSHIP_CONTAINMENT_HANDS_OFF_BUTTON = ("🔓 Не лезть", "rd_ownership_hands_off")
RD_OWNERSHIP_OUTPUT_OFF_BUTTON = ("⏹ Output OFF", "rd_ownership_output_off")

# Autonomous ownership actions are presented only from the app-aware HMI projection.
AUTONOMOUS_ENTRY_BUTTON = ("🔌 Автономный БП", "rd_autonomous_confirm")
AUTONOMOUS_EXIT_BUTTON = ("🤖 Вернуть управление боту", "rd_autonomous_exit")
AUTONOMOUS_RECONCILE_BUTTON = (
    "⚠️ Проверить AUTONOMOUS / вернуть боту",
    "rd_autonomous_exit",
)

# Managed external-Mix HMI labels and established callback destinations.
MANAGED_MIX_ACTIVE_TITLE = "RD6018 · MIX ПОД УПРАВЛЕНИЕМ"
MANAGED_MIX_OFF_PENDING_TITLE = "RD6018 · MIX · OFF PENDING"
MANAGED_MIX_STOP_BUTTON = ("⏹ Остановить Mix", "operator_managed_mix_stop")
MANAGED_MIX_DETAILS_BUTTON = ("ℹ Подробнее", "operator_details")
MANAGED_MIX_GRAPH_BUTTON = ("📈 График", "operator_graph")
MANAGED_MIX_BATTERY_BUTTON = ("🔋 АКБ", "v2_batteries")
MANAGED_MIX_ENTRY_BUTTON = ("🎯 Забрать Mix под управление", "rd_managed_mix")
MANAGED_MIX_STATUS_BUTTON = ("🎯 Статус Managed Mix", "rd_managed_mix_status")
