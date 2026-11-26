"""Convert eligibility rule results into the existing application read model."""
from application.operator_actions import OperatorActionSpec, OperatorActionsView

def action_view(available, disabled=(), reason="not_available_in_current_state"):
    disabled = tuple(disabled)
    return OperatorActionsView(
        tuple(OperatorActionSpec(action) for action in available),
        disabled,
        {action.value: reason for action in disabled},
    )
