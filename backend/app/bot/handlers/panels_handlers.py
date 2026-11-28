# backend/app/bot/handlers/panels_handlers.py
# =====================================================================
# Назначение кода:
# /panels — краткая сводка по панелям.
# Канон UI: активация панели, без покупки.
# =====================================================================

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from app.bot.keyboards import kb__main__menu, kb_subscribe
from app.bot.texts import t
from app.crud.user_crud import get_user_by_telegram_subject
from app.deps import d8
from app.services.panels_service import panels_summary
from sqlalchemy.ext.asyncio import AsyncSession

router = Router()


async def _gate_subscribe(
    message: Message,
    required_channel_id: int | None,
    is_subscribed: bool,
    required_channel_username: str | None,
) -> bool:
    """Блокирует доступ, если включена обязательная подписка.

    Инварианты и безопасность:
    - Повторный вызов не создаёт дубли.
    - Денежные значения учитываются с точностью d8.
    - Баланс/банк меняются только через транзакционный сервис.
    """

    if required_channel_id and not is_subscribed:
        channel = required_channel_username or str(required_channel_id)
        await message.answer(
            t(
                "subscribe.required",
                channel=channel,
            ),
            reply_markup=kb_subscribe(required_channel_username),
        )
        return True

    return False


@router.message(Command("panels"))
async def cmd_panels(
    message: Message,
    db: AsyncSession,
    is_subscribed: bool = True,
    required_channel_username: str | None = None,
    required_channel_id: int | None = None,
) -> None:
    """Команда /panels: сводка по панелям пользователя."""

    if not message.from_user:
        return

    if await _gate_subscribe(
        message,
        required_channel_id,
        is_subscribed,
        required_channel_username,
    ):
        return

    sender = message.from_user
    tg_id = int(sender.id)
    user = await get_user_by_telegram_subject(
        db,
        tg_id=tg_id,
    )
    if not user:
        await message.answer("Пользователь не найден. Нажмите /start")
        return

    summ = await panels_summary(
        db,
        global_id=int(user.global_id),
    )
    text = t(
        "panels.summary",
        count=str(summ.get("active_panels_count", 0)),
        per_sec=d8(summ.get("gen_per_sec_kwh", 0)),
        avail_kwh=d8(getattr(user, "available_kwh", 0)),
    )

    require_subscribe = bool(required_channel_id)
    await message.answer(
        text,
        reply_markup=kb__main__menu(
            require_subscribe=require_subscribe,
        ),
    )
