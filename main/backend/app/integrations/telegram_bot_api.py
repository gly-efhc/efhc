from __future__ import annotations

from dataclasses import dataclass

from app.core.config_core import get_settings
from app.core.logging_core import get_logger

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class SubscriptionCheck:
    chat: str
    subscribed: bool


class TelegramAPI:
    """Minimal Telegram API adapter for tasks checks.

    Import-safe runtime adapter. In degraded environments it logs and
    returns a conservative result only when explicitly used.
    """

    async def batch_is_user_subscribed(
        self,
        *,
        tg_id: int,
        chats: list[str],
    ) -> list[SubscriptionCheck]:
        try:
            from aiogram import Bot
        except Exception as err:
            logger.warning(
                "TelegramAPI import unavailable recipient=<redacted>: %s",
                err,
            )
            raise

        token = str(getattr(settings, "BOT_TOKEN", "") or "")
        if not token:
            raise RuntimeError("BOT_TOKEN is not configured")

        bot = Bot(token=token)
        results: list[SubscriptionCheck] = []
        try:
            for chat in chats:
                member = await bot.get_chat_member(
                    chat,
                    tg_id,
                )
                status = str(
                    getattr(member, "status", "") or ""
                ).lower()
                subscribed = status in {
                    "creator",
                    "administrator",
                    "member",
                    "restricted",
                }
                results.append(
                    SubscriptionCheck(
                        chat=str(chat),
                        subscribed=subscribed,
                    )
                )
            return results
        finally:
            await bot.session.close()
