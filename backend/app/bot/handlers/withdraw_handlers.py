# backend/app/bot/handlers/withdraw_handlers.py
# ----------------------------------------------------------------------
# Назначение кода:
# /withdraw — навигация к выводу EFHC через WebApp.
#
# Канон:
# • Заявка на вывод — денежная операция и делается только через API с
#   Idempotency-Key.
# ----------------------------------------------------------------------

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
    """Проверяет подписку и показывает кнопку
    подписки при необходимости.

    Инварианты:
    - Повторный вызов не должен создавать дубли (идемпотентность).
    - Денежные значения EFHC учитываются с точностью d8 и ROUND_DOWN.
    - Баланс/банк изменяются только через transactions_service.
    """
    if required_channel_id and not is_subscribed:
        channel = required_channel_username or str(required_channel_id)
        await message.answer(
            t("subscribe.required", channel=channel),
            reply_markup=kb_subscribe(required_channel_username),
        )
        return True
    return False


@router.message(Command("withdraw"))
async def cmd_withdraw(
    message: Message,
    db: AsyncSession,
    is_subscribed: bool = True,
    required_channel_username: str | None = None,
    required_channel_id: int | None = None,
) -> None:
    """Команда /withdraw — переводит пользователя
    в WebApp для вывода."""
    if await _gate_subscribe(
        message,
        required_channel_id,
        is_subscribed,
        required_channel_username,
    ):
        return

    require_subscribe = bool(required_channel_id)
    await message.answer(
        "💸 Вывод оформляется в WebApp 👇",
        reply_markup=kb__main__menu(
            require_subscribe=require_subscribe
        ),
    )

    _ = db
