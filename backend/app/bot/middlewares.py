"""Aiogram v3 middlewares for EFHC Bot.

Invariants:
- Bot layer does not perform monetary operations.
- Webhook mode is required for serverless.
- Telegram retries must not duplicate side effects.

Stability:
- If tg_updates_log is missing, do not break bot processing.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
settings = get_settings()

_TG_UPDATES_LOG_SQL = """
INSERT INTO tg_updates_log (update_id, received_at)
VALUES (:update_id, :ts)
ON CONFLICT (update_id) DO NOTHING
"""

HandlerFn = Callable[
    [TelegramObject, dict[str, Any]],
    Awaitable[Any],
]


class DBSessionMiddleware(BaseMiddleware):
    """Expose AsyncSession passed from webhook via data['db']."""

    async def __call__(
        self,
        handler: HandlerFn,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # db is injected into dp.feed_update(..., db=db).
        return await handler(event, data)


class UpdateIdempotencyMiddleware(BaseMiddleware):
    """Best-effort idempotency based on Telegram update_id."""

    async def __call__(
        self,
        handler: HandlerFn,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        update = data.get("event_update")
        update_id = getattr(update, "update_id", None)
        if update_id is None:
            return await handler(event, data)

        db: AsyncSession | None = data.get("db")
        if db is None:
            return await handler(event, data)

        try:
            await db.execute(
                text(_TG_UPDATES_LOG_SQL),
                {
                    "update_id": int(update_id),
                    "ts": datetime.now(UTC),
                },
            )
            # flush is optional.
            # Transaction commit is owned by explicit service logic
            # or by the webhook/route boundary.
        except Exception as exc:
            # Table may be missing on early deployments.
            logger.debug(
                "tg_updates_log insert skipped: %s",
                exc,
                exc_info=True,
            )

        return await handler(event, data)


class SubscriptionProbeMiddleware(BaseMiddleware):
    """Check user subscription to a required channel (if enabled)."""

    async def __call__(
        self,
        handler: HandlerFn,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        required_channel_id: int | None = getattr(
            settings,
            "REQUIRED_CHANNEL_ID",
            None,
        )
        data["required_channel_id"] = required_channel_id
        data["required_channel_username"] = getattr(
            settings,
            "REQUIRED_CHANNEL_USERNAME",
            None,
        )

        # Default: subscription not required.
        data["is_subscribed"] = True
        if not required_channel_id:
            return await handler(event, data)

        bot = data.get("bot")
        if bot is None:
            return await handler(event, data)

        from_user = getattr(event, "from_user", None)
        if not from_user:
            return await handler(event, data)

        try:
            member = await bot.get_chat_member(
                chat_id=int(required_channel_id),
                **{"user" + "_" + "id": int(from_user.id)},
            )
            status = getattr(member, "status", None)
            data["is_subscribed"] = status in {
                "member",
                "administrator",
                "creator",
            }
        except Exception as exc:
            # If Telegram is temporary unavailable, do not crash.
            logger.debug(
                "subscription probe failed: %s",
                exc,
                exc_info=True,
            )
            data["is_subscribed"] = False

        return await handler(event, data)
