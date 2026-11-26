# backend/app/bot/handlers/hub_handlers.py
# ======================================================================
# Назначение кода:
# /hub — навигация в Hub WebApp.
# ======================================================================

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from app.bot.keyboards import kb__main__menu, kb_subscribe
from app.bot.texts import t
from sqlalchemy.ext.asyncio import AsyncSession

router = Router()


async def _gate_subscribe(
    message: Message,
    required_channel_id: int | None,
    is_subscribed: bool,
    required_channel_username: str | None,
) -> bool:
    """Проверка подписки на обязательный канал (если он задан).

    Если канал обязателен и подписки нет — отправляет пользователю
    сообщение с кнопкой подписки и возвращает True.

    Инварианты:
    - Повторный вызов не создаёт дублей (идемпотентность по ключам).
    - Денежные значения учитываются с d8 и ROUND_DOWN (если применимо).
    """
    if required_channel_id and not is_subscribed:
        channel = required_channel_username or str(required_channel_id)
        await message.answer(
            t("subscribe.required", channel=channel),
            reply_markup=kb_subscribe(required_channel_username),
        )
        return True
    return False


@router.message(Command("hub"))
async def cmd_hub(
    message: Message,
    db: AsyncSession,  # noqa: F401
    is_subscribed: bool = True,
    required_channel_username: str | None = None,
    required_channel_id: int | None = None,
) -> None:
    """Открывает WebApp Hub."""
    if await _gate_subscribe(
        message,
        required_channel_id,
        is_subscribed,
        required_channel_username,
    ):
        return

    await message.answer(
        "🧭 Hub открывается в WebApp 👇",
        reply_markup=kb__main__menu(
            require_subscribe=bool(required_channel_id),
        ),
    )
