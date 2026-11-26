# backend/app/bot/handlers/admin/admin_users_handlers.py
# ======================================================================
# Назначение кода:
# Админ-команда admin_users: безопасная точка входа в админ-операции
# через WebApp.
# Канон: админ-логика и деньги выполняются ТОЛЬКО через backend API и
# services слой.
# ======================================================================
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


@router.message(Command("admin_users"))
async def handler(message: Message, db: AsyncSession) -> None:
    """Показывает точку входа в Admin → Users (WebApp)."""
    if not message.from_user:
        return
    if not await telegram_sender_has_admin_access(db, message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return

    await message.answer(
        "👥 Управление пользователями доступно в WebApp → "
        "Admin → Users.",
        reply_markup=kb__main__menu(),
    )
