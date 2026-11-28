"""Telegram bot package exports with lazy aiogram loading.

Importing ``app.bot.fsm`` must not require aiogram.
The heavy bot runtime loads only when webhook helpers are called.
"""

from __future__ import annotations

from typing import Any


def get_bot(*args: Any, **kwargs: Any) -> Any:
    from app.bot.bot import get_bot as _get_bot

    return _get_bot(*args, **kwargs)


def get_dispatcher(*args: Any, **kwargs: Any) -> Any:
    from app.bot.bot import get_dispatcher as _get_dispatcher

    return _get_dispatcher(*args, **kwargs)


async def process_update(*args: Any, **kwargs: Any) -> Any:
    from app.bot.bot import process_update as _process_update

    return await _process_update(*args, **kwargs)


__all__ = ["get_bot", "get_dispatcher", "process_update"]
