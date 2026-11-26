"""Public FSM package API for EFHC bot."""

from app.bot.fsm.backend import MemoryStateBackend, StateBackend
from app.bot.fsm.decorators import (
    Handler,
    advance_state,
    clear_state_after,
    require_state,
)
from app.bot.fsm.dto import (
    DEFAULT_GC_INTERVAL_SECONDS,
    DEFAULT_STATE_TTL_SECONDS,
    MAX_STATE_DATA_BYTES,
    BotStates,
    ConversationState,
    StateKey,
)
from app.bot.fsm.manager import StateManager, get_state_manager

__all__ = [
    "DEFAULT_GC_INTERVAL_SECONDS",
    "DEFAULT_STATE_TTL_SECONDS",
    "MAX_STATE_DATA_BYTES",
    "BotStates",
    "ConversationState",
    "Handler",
    "MemoryStateBackend",
    "StateBackend",
    "StateKey",
    "StateManager",
    "advance_state",
    "clear_state_after",
    "get_state_manager",
    "require_state",
]
