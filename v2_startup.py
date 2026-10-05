"""Historical START compatibility facade.

Production START ownership moved to :mod:`application.start_transaction_service`
during ERADICATION-09. This module intentionally re-exports the accepted public
helpers for compatibility tests and archived callers; production code must not
import it.
"""

from application.start_transaction_service import (
    INITIAL_MAIN_THRESHOLD_V,
    _confirm_failed_start_is_off,
    _execution_identity,
    _execution_intent,
    _select_initial_auto_target,
    start_profile_transactional,
)

__all__ = [
    "INITIAL_MAIN_THRESHOLD_V",
    "_confirm_failed_start_is_off",
    "_execution_identity",
    "_execution_intent",
    "_select_initial_auto_target",
    "start_profile_transactional",
]
