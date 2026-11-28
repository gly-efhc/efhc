# backend/app/bot/handlers/admin/admin_stats_handlers.py
# ----------------------------------------------------------------------
# Назначение кода:
# /admin_stats — вход в раздел Admin → Reports в WebApp.
# ----------------------------------------------------------------------

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from app.bot.handlers.admin.admin_access import (
    telegram_sender_has_admin_access,
)
from app.bot.keyboards import kb__main__menu
from sqlalchemy.ext.asyncio import AsyncSession

router = Router()


@router.message(Command("admin_stats"))
async def handler(message: Message, db: AsyncSession) -> None:
    """Команда /admin_stats — отдаёт навигацию к WebApp."""
    if not message.from_user:
        return

    if not await telegram_sender_has_admin_access(db, message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return

    await message.answer(
        "📊 Статистика доступна в WebApp → Admin → Reports.",
        reply_markup=kb__main__menu(),
    )
