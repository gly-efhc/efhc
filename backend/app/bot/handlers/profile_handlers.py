# backend/app/bot/handlers/profile_handlers.py
# ======================================================================
# Назначение кода:
# /profile — показать профиль пользователя.
# Без денежных операций.
# ======================================================================

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
    """Проверка подписки.

    Если подписки нет —
    показывает подсказку
    и возвращает True.
    """
    if required_channel_id and not is_subscribed:
        channel = required_channel_username or str(required_channel_id)
        await message.answer(
            t("subscribe.required", channel=channel),
            reply_markup=kb_subscribe(required_channel_username),
        )
        return True
    return False


@router.message(Command("profile"))
async def cmd_profile(
    message: Message,
    db: AsyncSession,
    is_subscribed: bool = True,
    required_channel_username: str | None = None,
    required_channel_id: int | None = None,
) -> None:
    """Показывает профиль пользователя.

    Денежные операции не выполняются.
    """
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
    user = await get_user_by_telegram_subject(db, tg_id=tg_id)
    if not user:
        await message.answer(
            "Профиль не найден. Нажмите /start",
            reply_markup=kb__main__menu(
                require_subscribe=bool(required_channel_id),
            ),
        )
        return

    summ = await panels_summary(
        db,
        global_id=int(user.global_id),
    )
    vip_flag = "VIP" if bool(getattr(user, "is_vip", False)) else "NO"
    text = (
        t("profile.header")
        + "\n"
        + t(
            "profile.lines",
            tg_id=str(tg_id),
            vip_flag=vip_flag,
            panels=str(summ.get("active_panels_count", 0)),
            avail_kwh=d8(getattr(user, "available_kwh", 0)),
            total_kwh=d8(getattr(user, "total_generated_kwh", 0)),
        )
    )
    await message.answer(
        text,
        reply_markup=kb__main__menu(
            require_subscribe=bool(required_channel_id),
        ),
    )
