# backend/app/bot/handlers/referrals_handlers.py
# ======================================================================
# Назначение кода:
# /referrals — статистика по рефералам.
# ======================================================================

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from app.bot.keyboards import kb__main__menu, kb_subscribe
from app.bot.texts import t
from app.crud.user_crud import get_user_by_telegram_subject
from app.services.referral_service import get_referral_stats
from sqlalchemy.ext.asyncio import AsyncSession

router = Router()


async def _gate_subscribe(
    message: Message,
    required_channel_id: int | None,
    is_subscribed: bool,
    required_channel_username: str | None,
) -> bool:
    """Асинхронная функция `_gate_subscribe` выполняет операцию.
    Назначение: бизнес‑логика соответствующего модуля.

    Параметры:
    - `message` (Message): входной параметр.
    - `required_channel_id` (Optional[int]): входной параметр.
    - `is_subscribed` (bool): входной параметр.
    - `required_channel_username` (Optional[str]): входной параметр.

    Возвращает:
    - Значение типа/структуры: bool.

    Инварианты и безопасность:
    - Повторный вызов не должен создавать дубли (идемпотентность —
      ключи/уникальные ограничения).
    - Денежные значения EFHC: точность d8, округление вниз (ROUND_DOWN).
    - Операции баланса/банка проходят через transactions_service.
    """
    if required_channel_id and not is_subscribed:
        await message.answer(
            t(
                "subscribe.required",
                channel=(
                    required_channel_username
                    or str(required_channel_id)
                ),
            ),
            reply_markup=kb_subscribe(required_channel_username),
        )
        return True
    return False


@router.message(Command("referrals"))
async def cmd_referrals(
    message: Message,
    db: AsyncSession,
    is_subscribed: bool = True,
    required_channel_username: str | None = None,
    required_channel_id: int | None = None,
) -> None:
    """Асинхронная функция `cmd_referrals` выполняет операцию в контуре.
    Назначение: бизнес‑логика соответствующего модуля.

    Параметры:
    - `message` (Message): входной параметр.
    - `db` (AsyncSession): входной параметр.
    - `is_subscribed` (bool): входной параметр.
    - `required_channel_username` (Optional[str]): входной параметр.
    - `required_channel_id` (Optional[int]): входной параметр.

    Возвращает:
    - Значение типа/структуры: None.

    Инварианты и безопасность:
    - Повторный вызов не должен создавать дубли (идемпотентность —
      ключи/уникальные ограничения).
    - Денежные значения EFHC: точность d8, округление вниз (ROUND_DOWN).
    - Операции баланса/банка проходят через transactions_service.
    """
    if not message.from_user:
        return
    tg_id = int(message.from_user.id)
    if await _gate_subscribe(
        message,
        required_channel_id,
        is_subscribed,
        required_channel_username,
    ):
        return

    user = await get_user_by_telegram_subject(
        db,
        tg_id=tg_id,
    )
    if not user:
        await message.answer("Пользователь не найден. Нажмите /start")
        return

    stats = await get_referral_stats(
        db,
        inviter_global_id=int(user.global_id),
    )
    inactive_count = max(
        int(stats.total_referrals) - int(stats.active_referrals),
        0,
    )
    lines = [
        t("referrals.header"),
        t(
            "referrals.active.count",
            count=str(stats.active_referrals),
        ),
        t(
            "referrals.inactive.count",
            count=str(inactive_count),
        ),
    ]
    await message.answer(
        "\n".join(lines),
        reply_markup=kb__main__menu(
            require_subscribe=bool(required_channel_id),
        ),
    )
