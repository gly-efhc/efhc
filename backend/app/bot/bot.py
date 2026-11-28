"""Telegram Bot (aiogram v3).

WebHook: POST /api/tg/webhook (см. routes/system_routes.py).

Инварианты:
- Денежных операций в bot-слое нет.
- Доступ к WebApp может требовать подписку (REQUIRED_CHANNEL_ID).
- Идемпотентность update_id: tg_updates_log.update_id UNIQUE.
"""

from __future__ import annotations

from typing import Any, cast

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.types import Update
from app.bot.handlers.admin_handlers import (
    router as admin_router,
)
from app.bot.handlers.ads_handlers import router as ads_router
from app.bot.handlers.balance_handlers import (
    router as balance_router,
)
from app.bot.handlers.errors_handlers import (
    router as errors_router,
)
from app.bot.handlers.exchange_handlers import (
    router as exchange_router,
)
from app.bot.handlers.health_handlers import (
    router as health_router,
)
from app.bot.handlers.hub_handlers import router as hub_router
from app.bot.handlers.panels_handlers import (
    router as panels_router,
)
from app.bot.handlers.profile_handlers import (
    router as profile_router,
)
from app.bot.handlers.ranks_handlers import (
    router as ranks_router,
)
from app.bot.handlers.referrals_handlers import (
    router as referrals_router,
)
from app.bot.handlers.start_handlers import (
    router as start_router,
)
from app.bot.handlers.subscriptions_handlers import (
    router as subscriptions_router,
)
from app.bot.handlers.tasks_handlers import (
    router as tasks_router,
)
from app.bot.handlers.webapp_handlers import (
    router as webapp_router,
)
from app.bot.handlers.withdraw_handlers import (
    router as withdraw_router,
)
from app.bot.middlewares import (
    DBSessionMiddleware,
    SubscriptionProbeMiddleware,
    UpdateIdempotencyMiddleware,
)
from app.bot.texts import t
from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
settings = get_settings()

_bot: Bot | None = None
_dp: Dispatcher | None = None


def get_bot() -> Bot:
    """Ленивая инициализация Bot."""
    global _bot
    if _bot is None:
        token = getattr(settings, "BOT_TOKEN", None)
        if not token:
            msg = (
                "BOT_TOKEN is not configured "
                "(TELEGRAM_BOT_TOKEN/BOT_TOKEN)."
            )
            raise RuntimeError(msg)
        _bot = Bot(token=token, parse_mode=ParseMode.HTML)
    return _bot


def get_dispatcher() -> Dispatcher:
    """Ленивая инициализация Dispatcher и роутеров."""
    global _dp
    if _dp is None:
        dp = Dispatcher()
        dp.update.middleware(DBSessionMiddleware())
        dp.update.middleware(UpdateIdempotencyMiddleware())
        dp.message.middleware(SubscriptionProbeMiddleware())
        # Ошибки и health должны быть первыми
        dp.include_router(errors_router)
        dp.include_router(health_router)
        # Админ — до пользовательских команд
        dp.include_router(admin_router)

        # Пользовательские роутеры
        dp.include_router(start_router)
        dp.include_router(webapp_router)
        dp.include_router(profile_router)
        dp.include_router(balance_router)
        dp.include_router(panels_router)
        dp.include_router(exchange_router)
        dp.include_router(hub_router)
        dp.include_router(tasks_router)
        dp.include_router(referrals_router)
        dp.include_router(ranks_router)
        dp.include_router(withdraw_router)
        dp.include_router(subscriptions_router)
        dp.include_router(ads_router)

        _dp = dp
    return _dp


async def process_update(
    db: AsyncSession,
    payload: dict[str, Any],
) -> None:
    """Единая точка входа для FastAPI webhook."""
    try:
        bot = get_bot()
        dp = get_dispatcher()

        update = Update.model_validate(payload)
        # db прокидывается в handlers: любой handler может принять db.
        # AsyncSession
        await dp.feed_update(bot, update, db=db)
    except Exception as e:
        logger.exception("Telegram update processing error: %s", e)
        raise


async def require_subscription_text(
    data: dict[str, Any],
) -> str | None:
    """Текст "нужно подписаться" для включенного правила."""
    required_channel_id = data.get("required_channel_id")
    if not required_channel_id:
        return None
    if data.get("is_subscribed") is True:
        return None
    channel_username = data.get("required_channel_username")
    channel = channel_username or str(required_channel_id)
    return cast(str, t("subscribe.required", channel=channel))
