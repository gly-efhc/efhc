# backend/app/bot/handlers/webapp_handlers.py
# ======================================================================
# Назначение кода:
# Хэндлеры открытия WebApp и разделов через Telegram-бота (aiogram v3).
#
# Канон/инварианты:
# • Бот-слой не делает денег и не меняет балансы.
# • Кнопки только открывают WebApp (frontend) по URL из WEBAPP_URL.
# • Если включена обязательная подписка — блокируем доступ до подписки.
# ======================================================================

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from app.bot.keyboards import kb__main__menu, kb_subscribe
from app.bot.texts import t
from sqlalchemy.ext.asyncio import AsyncSession

router = Router()


@router.message(Command("webapp"))
async def cmd_webapp(
    message: Message,
    db: AsyncSession,  # noqa: F401 (db доступен в каждом handler)
    is_subscribed: bool = True,
    required_channel_username: str | None = None,
    required_channel_id: int | None = None,
) -> None:
    """Открывает WebApp (с проверкой подписки, если включена)."""
    if required_channel_id and not is_subscribed:
        channel = required_channel_username or str(required_channel_id)
        await message.answer(
            t("subscribe.required", channel=channel),
            reply_markup=kb_subscribe(required_channel_username),
        )
        return

    await message.answer(
        "Открывайте WebApp кнопками ниже 👇",
        reply_markup=kb__main__menu(
            require_subscribe=bool(required_channel_id),
        ),
    )
