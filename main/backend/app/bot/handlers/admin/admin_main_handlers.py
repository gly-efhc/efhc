# backend/app/bot/handlers/admin/admin_main_handlers.py
# ----------------------------------------------------------------------
# Назначение кода:
# /admin — безопасная точка входа в админ-операции через WebApp.
# Канон: админ-логика и деньги выполняются через backend API + services.
# ----------------------------------------------------------------------

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from app.bot.handlers.admin.admin_access import (
    telegram_sender_has_admin_access,
)
from app.bot.keyboards import kb_admin_entry
from sqlalchemy.ext.asyncio import AsyncSession

router = Router()


@router.message(Command("admin"))
async def handler(message: Message, db: AsyncSession) -> None:
    """Команда /admin — отдаёт ссылку на админ-панель в WebApp."""
    if not message.from_user:
        return

    if not await telegram_sender_has_admin_access(db, message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return

    await message.answer(
        "🛠 Откройте Admin Hub в WebApp кнопкой ниже.",
        reply_markup=kb_admin_entry(),
    )
