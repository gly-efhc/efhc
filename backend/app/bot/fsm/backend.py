"""FSM backend contracts and in-memory fallback storage."""

from __future__ import annotations

import asyncio
import copy
from typing import Protocol, runtime_checkable

from app.bot.fsm.dto import ConversationState, StateKey
from app.lib.time import utcnow


@runtime_checkable
class StateBackend(Protocol):
    """Contract for optional external FSM state storage."""

    async def get(
        self,
        key: StateKey,
    ) -> ConversationState | None:
        ...

    async def set(
        self,
        key: StateKey,
        value: ConversationState,
    ) -> None:
        ...

    async def clear(self, key: StateKey) -> None:
        ...

    async def cleanup(self) -> int:
        """Remove expired records and return removed count."""
        return 0


class MemoryStateBackend:
    """Process-local TTL backend for bot navigation state."""

    def __init__(self) -> None:
        self._store: dict[StateKey, ConversationState] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: StateKey) -> ConversationState | None:
        async with self._lock:
            state = self._store.get(key)
            if not state:
                return None
            if state.is_expired():
                self._store.pop(key, None)
                return None
            return copy.deepcopy(state)

    async def set(
        self,
        key: StateKey,
        value: ConversationState,
    ) -> None:
        async with self._lock:
            self._store[key] = copy.deepcopy(value)

    async def clear(self, key: StateKey) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def cleanup(self) -> int:
        async with self._lock:
            now = utcnow().timestamp()
            expired = [
                key
                for key, state in self._store.items()
                if state.is_expired(now)
            ]
            for key in expired:
                self._store.pop(key, None)
            return len(expired)
