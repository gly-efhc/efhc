"""FSM manager and singleton factory."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from typing import Any

from app.bot.fsm.backend import MemoryStateBackend, StateBackend
from app.bot.fsm.dto import (
    DEFAULT_GC_INTERVAL_SECONDS,
    MAX_STATE_DATA_BYTES,
    BotStates,
    ConversationState,
    StateKey,
)
from app.core.async_tasks import create_logged_task

logger = logging.getLogger(__name__)


class StateManager:
    """High-level bot FSM API with primary and fallback storage."""

    _LOCK_STRIPES = 256

    def __init__(self, backend: StateBackend | None = None) -> None:
        self._primary = backend
        self._fallback = MemoryStateBackend()
        self._gc_task: asyncio.Task[Any] | None = None
        self._gc_interval = DEFAULT_GC_INTERVAL_SECONDS
        self._locks = [
            asyncio.Lock() for _ in range(self._LOCK_STRIPES)
        ]

    @staticmethod
    def make_key(tg_id: int, chat_id: int) -> StateKey:
        return (int(tg_id), int(chat_id))

    def _key_lock(self, key: StateKey) -> asyncio.Lock:
        """Вернуть process-local lock для атомарного перехода состояния."""
        return self._locks[hash(key) % len(self._locks)]

    async def _get(self, key: StateKey) -> ConversationState | None:
        if self._primary:
            try:
                state = await self._primary.get(key)
                if state:
                    return state
            except Exception as exc:
                logger.warning(
                    "StateManager: primary.get failed; fallback: %s",
                    exc,
                )
        return await self._fallback.get(key)

    async def _set(
        self,
        key: StateKey,
        state: ConversationState,
    ) -> None:
        ok_primary = False
        if self._primary:
            try:
                await self._primary.set(key, state)
                ok_primary = True
            except Exception as exc:
                logger.warning(
                    "StateManager: primary.set failed; fallback: %s",
                    exc,
                )
        try:
            await self._fallback.set(key, state)
        except Exception as exc:
            logger.error("StateManager: fallback.set failed: %s", exc)
            if ok_primary:
                return
            raise

    async def _clear(self, key: StateKey) -> None:
        if self._primary:
            try:
                await self._primary.clear(key)
            except Exception as exc:
                logger.warning(
                    "StateManager: primary.clear failed: %s",
                    exc,
                )
        try:
            await self._fallback.clear(key)
        except Exception as exc:
            logger.error("StateManager: fallback.clear failed: %s", exc)

    async def get(self, tg_id: int, chat_id: int) -> ConversationState:
        key = self.make_key(tg_id, chat_id)
        state = await self._get(key)
        if not state:
            return ConversationState(state=BotStates.IDLE)
        return state

    async def set(
        self,
        tg_id: int,
        chat_id: int,
        state: str,
        data: dict[str, Any] | None = None,
        *,
        ttl: int | None = None,
    ) -> ConversationState:
        safe = self._sanitize_data(data or {})
        item = ConversationState(state=state, data=safe)
        item.touch(ttl)
        await self._set(self.make_key(tg_id, chat_id), item)
        return item

    async def clear(self, tg_id: int, chat_id: int) -> None:
        await self._clear(self.make_key(tg_id, chat_id))

    async def update_data(
        self,
        tg_id: int,
        chat_id: int,
        patch: dict[str, Any],
        *,
        ttl: int | None = None,
    ) -> ConversationState:
        key = self.make_key(tg_id, chat_id)
        async with self._key_lock(key):
            state = await self._get(key) or ConversationState()
            merged = dict(state.data or {})
            merged.update(patch or {})
            state.data = self._sanitize_data(merged)
            state.touch(ttl)
            await self._set(key, state)
            return state

    async def transition(
        self,
        tg_id: int,
        chat_id: int,
        expected_state: str | None,
        next_state: str,
        *,
        data: dict[str, Any] | None = None,
        ttl: int | None = None,
    ) -> tuple[bool, ConversationState]:
        key = self.make_key(tg_id, chat_id)
        async with self._key_lock(key):
            state = await self._get(key) or ConversationState()
            if expected_state is not None and state.state != expected_state:
                return False, state
            state.state = next_state
            if data:
                merged = dict(state.data or {})
                merged.update(data)
                state.data = self._sanitize_data(merged)
            state.touch(ttl)
            await self._set(key, state)
            return True, state

    async def start_background_gc(self) -> None:
        if self._gc_task and not self._gc_task.done():
            return

        async def _gc_loop() -> None:
            while True:
                try:
                    if self._primary:
                        try:
                            removed = await self._primary.cleanup()
                            if removed:
                                logger.debug(
                                    "primary GC removed %s",
                                    removed,
                                )
                        except Exception as exc:
                            logger.debug(
                                "StateManager: primary GC failed: %s",
                                exc,
                            )
                    try:
                        removed_fb = await self._fallback.cleanup()
                        if removed_fb:
                            logger.debug(
                                "StateManager: fallback GC removed %s",
                                removed_fb,
                            )
                    except Exception as exc:
                        logger.debug(
                            "StateManager: fallback GC failed: %s",
                            exc,
                        )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.debug("StateManager GC loop error: %s", exc)
                await asyncio.sleep(self._gc_interval)

        self._gc_task = create_logged_task(
            _gc_loop(),
            name="bot_state_gc",
        )

    async def stop_background_gc(self) -> None:
        """Остановить фоновую GC-задачу, принадлежащую lifecycle владельцу."""
        task = self._gc_task
        self._gc_task = None
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    def _sanitize_data(self, data: dict[str, Any]) -> dict[str, Any]:
        safe = dict(data or {})
        try:
            payload = json.dumps(
                safe,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        except Exception:
            safe = {
                key: value
                if isinstance(
                    value,
                    str | int | float | bool | type(None),
                )
                else str(value)
                for key, value in safe.items()
            }
            payload = json.dumps(
                safe,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        if len(payload) <= MAX_STATE_DATA_BYTES:
            return safe

        for key in list(safe):
            if key.lower() in {"debug", "trace", "raw", "extra"}:
                safe.pop(key, None)
        payload = json.dumps(
            safe,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        if len(payload) <= MAX_STATE_DATA_BYTES:
            return safe

        trimmed: dict[str, Any] = {}
        for key, value in safe.items():
            if isinstance(value, str):
                trimmed[key] = (
                    value[:255] + "..." if len(value) > 256 else value
                )
            elif isinstance(value, int | float | bool) or value is None:
                trimmed[key] = value
            else:
                trimmed[key] = str(value)[:255] + "..."
        payload = json.dumps(
            trimmed,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        while trimmed and len(payload) > MAX_STATE_DATA_BYTES:
            trimmed.pop(next(iter(trimmed.keys())), None)
            payload = json.dumps(
                trimmed,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        return trimmed


_global_state_manager: StateManager | None = None


def get_state_manager(
    backend: StateBackend | None = None,
) -> StateManager:
    """Return process singleton StateManager."""
    global _global_state_manager
    if _global_state_manager is None:
        _global_state_manager = StateManager(backend=backend)
    return _global_state_manager
