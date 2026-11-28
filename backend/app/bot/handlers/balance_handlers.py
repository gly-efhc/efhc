# backend/app/bot/handlers/balance_handlers.py
"""Bot handler: /balance.

Показывает доступный баланс kWh/EFHC (без операций).
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from app.bot.keyboards import kb__main__menu, kb_subscribe
from app.bot.texts import t
from app.crud.user_crud import get_user_by_telegram_subject
from app.deps import d8
from sqlalchemy.ext.asyncio import AsyncSession

router = Router()


async def _gate_subscribe(
    message: Message,
    required_channel_id: int | None,
    is_subscribed: bool,
    required_channel_username: str | None,
) -> bool:
    """Возвращает True, если доступ заблокирован из‑за подписки."""
    if required_channel_id and not is_subscribed:
        channel = required_channel_username or str(required_channel_id)
        await message.answer(
            t("subscribe.required", channel=channel),
            reply_markup=kb_subscribe(required_channel_username),
        )
        return True
    return False


@router.message(Command("balance"))
async def cmd_balance(
    message: Message,
    db: AsyncSession,
    is_subscribed: bool = True,
    required_channel_username: str | None = None,
    required_channel_id: int | None = None,
) -> None:
    """Показывает баланс пользователя."""
    sender = message.from_user
    if not sender:
        return
    if await _gate_subscribe(
        message,
        required_channel_id,
        is_subscribed,
        required_channel_username,
    ):
        return

    user = await get_user_by_telegram_subject(
        db,
        tg_id=int(sender.id),
    )
    if not user:
        await message.answer("Пользователь не найден. Нажмите /start")
        return

    vip_flag = "VIP" if bool(getattr(user, "is_vip", False)) else "NO"
    username = sender.username or sender.full_name or "user"
    avail_kwh = d8(getattr(user, "available_kwh", 0))
    await message.answer(
        t(
            "welcome",
            username=username,
            vip_flag=vip_flag,
            panels="?",
            avail_kwh=avail_kwh,
        ),
        reply_markup=kb__main__menu(
            require_subscribe=bool(required_channel_id),
        ),
    )
