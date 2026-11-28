# backend/app/bot/handlers/subscriptions_handlers.py
# ======================================================================
# Назначение кода:
# /subscribe — показать требование подписки (если включено).
# ======================================================================

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from app.bot.keyboards import kb_subscribe
from app.bot.texts import t

router = Router()


@router.message(Command("subscribe"))
async def cmd_subscribe(
    message: Message,
    required_channel_username: str | None = None,
    required_channel_id: int | None = None,
) -> None:
    """Показывает требование подписки (если канал задан)."""
    if not required_channel_id:
        await message.answer("Подписка не требуется.")
        return

    channel = required_channel_username or str(required_channel_id)
    await message.answer(
        t("subscribe.required", channel=channel),
        reply_markup=kb_subscribe(required_channel_username),
    )
