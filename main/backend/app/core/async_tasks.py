"""Helpers for supervised background tasks.

Single policy for create_task():
- every spawned task gets a readable name;
- every task logs its exception;
- cancellation stays silent and expected.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Coroutine
from typing import Any, TypeVar, cast

from app.core.logging_core import get_logger

logger = get_logger(__name__)
T = TypeVar("T")


def create_logged_task(
    coro: Awaitable[T],
    *,
    name: str,
) -> asyncio.Task[T]:
    """Create task with canonical exception logging."""
    task: asyncio.Task[T] = asyncio.create_task(
        cast(Coroutine[Any, Any, T], coro),
        name=name,
    )

    def _done(done: asyncio.Task[T]) -> None:
        try:
            done.result()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception(
                "background task failed: %s",
                done.get_name(),
            )

    task.add_done_callback(_done)
    return task


__all__ = ["create_logged_task"]
