"""FSM decorators for Telegram bot handlers."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.bot.fsm.manager import get_state_manager

logger = logging.getLogger(__name__)

Handler = Callable[..., Awaitable[Any]]


def require_state(
    expected: str | None,
) -> Callable[[Handler], Handler]:
    """Allow handler execution only for the expected FSM state."""

    def _wrap(fn: Handler) -> Handler:
        async def _inner(*args: Any, **kwargs: Any) -> Any:
            tg_id = kwargs.get("tg_id")
            chat_id = kwargs.get("chat_id")
            if tg_id is None or chat_id is None:
                logger.debug(
                    "require_state: missing tg_id/chat_id in kwargs"
                )
                return await fn(*args, **kwargs)

            manager = get_state_manager()
            state = await manager.get(int(tg_id), int(chat_id))
            if expected is not None and state.state != expected:
                logger.debug(
                    "require_state: blocked (expected=%s, actual=%s)",
                    expected,
                    state.state,
                )
                return None
            return await fn(*args, **kwargs)

        return _inner  # type: ignore[return-value]

    return _wrap


def advance_state(
    next_state: str,
    *,
    ttl: int | None = None,
    patch: dict[str, Any] | None = None,
) -> Callable[[Handler], Handler]:
    """Move user to the next state after successful handler call."""

    def _wrap(fn: Handler) -> Handler:
        async def _inner(*args: Any, **kwargs: Any) -> Any:
            tg_id = kwargs.get("tg_id")
            chat_id = kwargs.get("chat_id")
            result = await fn(*args, **kwargs)
            if tg_id is None or chat_id is None:
                return result
            manager = get_state_manager()
            await manager.set(
                int(tg_id),
                int(chat_id),
                next_state,
                data=patch or {},
                ttl=ttl,
            )
            return result

        return _inner  # type: ignore[return-value]

    return _wrap


def clear_state_after(fn: Handler) -> Handler:
    """Clear user state after handler execution."""

    async def _inner(*args: Any, **kwargs: Any) -> Any:
        tg_id = kwargs.get("tg_id")
        chat_id = kwargs.get("chat_id")
        result = await fn(*args, **kwargs)
        if tg_id is not None and chat_id is not None:
            manager = get_state_manager()
            await manager.clear(int(tg_id), int(chat_id))
        return result

    return _inner  # type: ignore[return-value]
