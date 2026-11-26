"""Display strings for the existing charge journal formatter."""

JOURNAL_STAGE_NAMES = {
        "MAIN": "Основной заряд", "Main Charge": "Основной заряд",
        "MIX": "Финишный заряд", "Mix": "Финишный заряд",
        "DESULFATION": "Восстановление", "Десульфатация": "Восстановление",
        "SAFE_WAIT": "Безопасное ожидание", "Безопасное ожидание": "Безопасное ожидание",
        "PREP": "Подготовка", "COOLING": "Охлаждение", "DONE": "Завершение",
        "Idle": "Ожидание",
    }

JOURNAL_MILESTONE_LABELS = {
                "MAIN_HOLD_START": 'Imin принят; отсчёт от минимума',
                "MAIN_HOLD_RESET": 'Новый Imin; отсчёт от минимума заново',
                "MIX_IMIN_UPDATED": 'Новый минимум тока MIX',
                "MIX_VMAX_UPDATED": 'Новый максимум напряжения MIX',
                "MIX_STARTED": "Начат финишный заряд", "DELTA_CONFIRMED": "Подтверждён Delta",
                "DELTA_HOLD_START": "Началась выдержка после Delta",
                "DELTA_HOLD_RESTART": "Выдержка после Delta началась заново",
                "I_MIN_ACHIEVED": "Достигнут минимальный ток Imin",
                "IMIN_ACHIEVED": "Достигнут минимальный ток Imin",
            }

MAIN_MINIMUM_PREFIXES = {'MAIN_HOLD_START': 'Imin', 'MAIN_HOLD_RESET': 'RE Imin'}
