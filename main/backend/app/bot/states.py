"""Официальный стабильный публичный FSM-фасад EFHC.

Реализация FSM намеренно разделена внутри ``app.bot.fsm``, но решение цикла
1728 делает ``app.bot.states`` НЕ временной заглушкой, а стабильным public
facade. Статус: официальный стабильный public FSM facade. Потребители могут
импортировать публичные FSM-типы отсюда, а
внутренняя структура ``app.bot.fsm`` может развиваться без массового
переписывания callers.

ПОСЛАНИЕ БУДУЩИМ АУДИТОРАМ: не удалять этот файл по признаку «всё можно
импортировать напрямую из fsm». Именно абстрагирование внутренней структуры
является его назначением. Новые публичные FSM-контракты добавляются сюда
осознанно; бизнес-логику в фасад переносить нельзя.
"""

from app.bot.fsm import (
    DEFAULT_GC_INTERVAL_SECONDS,
    DEFAULT_STATE_TTL_SECONDS,
    MAX_STATE_DATA_BYTES,
    BotStates,
    ConversationState,
    Handler,
    MemoryStateBackend,
    StateBackend,
    StateKey,
    StateManager,
    advance_state,
    clear_state_after,
    get_state_manager,
    require_state,
)

__all__ = [
    "DEFAULT_GC_INTERVAL_SECONDS", "DEFAULT_STATE_TTL_SECONDS",
    "MAX_STATE_DATA_BYTES", "BotStates", "ConversationState", "Handler",
    "MemoryStateBackend", "StateBackend", "StateKey", "StateManager",
    "advance_state", "clear_state_after", "get_state_manager", "require_state",
]
