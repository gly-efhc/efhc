# backend/app/bot/handlers/exchange_handlers.py
# =====================================================================
# Назначение кода:
# /exchange — подсказка по обмену (kWh → EFHC) через WebApp.
#
# Канон:
# • Бот не выполняет обмен. Это денежная операция — только через API с
#   Idempotency-Key.
# =====================================================================

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
    """Проверка обязательной подписки.

    Возвращает True, если доступ заблокирован и пользователю показана
    кнопка подписки.

    Инварианты и безопасность:
    - Повторные вызовы не создают дублей (уникальные ключи/ограничения).
    - Денежные значения: d8 и округление вниз (ROUND_DOWN), если нужно.
    - Баланс/банк меняются только через transactions_service.
    """

    if required_channel_id and not is_subscribed:
        channel = required_channel_username or str(required_channel_id)
        await message.answer(
            t("subscribe.required", channel=channel),
            reply_markup=kb_subscribe(required_channel_username),
        )
        return True

    return False


@router.message(Command("exchange"))
async def cmd_exchange(
    message: Message,
    db: AsyncSession,  # noqa: F401
    is_subscribed: bool = True,
    required_channel_username: str | None = None,
    required_channel_id: int | None = None,
) -> None:
    """Показывает подсказку по обмену через WebApp (без выполнения).

    Инварианты и безопасность:
    - Повторные вызовы не создают дублей (уникальные ключи/ограничения).
    - Денежные значения: d8 и округление вниз (ROUND_DOWN), если нужно.
    - Баланс/банк меняются только через transactions_service.
    """

    blocked = await _gate_subscribe(
        message,
        required_channel_id,
        is_subscribed,
        required_channel_username,
    )
    if blocked:
        return

    await message.answer(
        t("exchange.preview", kwh="—", efhc="—"),
        reply_markup=kb__main__menu(
            require_subscribe=bool(required_channel_id),
        ),
    )
