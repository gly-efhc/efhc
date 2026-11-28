# backend/app/bot/handlers/health_handlers.py
# ----------------------------------------------------------------------
# Назначение кода:
# /health — быстрый тест доступности бота (не путать с HTTP /health).
# ----------------------------------------------------------------------

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


@router.message(Command("health"))
async def cmd_health(message: Message) -> None:
    """Проверка доступности бота на уровне Telegram-обработчика."""
    await message.answer("✅ EFHC Bot: ok")
