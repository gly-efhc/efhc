# backend/app/bot/handlers/tasks_handlers.py
# ======================================================================
# Назначение кода:
# /tasks — список доступных заданий (подтверждение делается в WebApp).
# ======================================================================

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from app.bot.keyboards import kb__main__menu, kb_subscribe
from app.bot.texts import t
from app.crud.user_crud import get_user_by_telegram_subject
from app.deps import d8
from app.services.tasks_service import list_available_tasks
from sqlalchemy.ext.asyncio import AsyncSession

router = Router()


async def _gate_subscribe(
    message: Message,
    required_channel_id: int | None,
    is_subscribed: bool,
    required_channel_username: str | None,
) -> bool:
    """Проверка подписки на обязательный канал (если он задан)."""
    if required_channel_id and not is_subscribed:
        channel = required_channel_username or str(required_channel_id)
        await message.answer(
            t("subscribe.required", channel=channel),
            reply_markup=kb_subscribe(required_channel_username),
        )
        return True
    return False


@router.message(Command("tasks"))
async def cmd_tasks(
    message: Message,
    db: AsyncSession,
    is_subscribed: bool = True,
    required_channel_username: str | None = None,
    required_channel_id: int | None = None,
) -> None:
    """Показывает список заданий (TOP-10) и краткую подсказку."""
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
    db_rec = await get_user_by_telegram_subject(db, tg_id=tg_id)
    if not db_rec:
        await message.answer("Пользователь не найден. Нажмите /start")
        return

    try:
        items = await list_available_tasks(
            db,
            global_id=int(db_rec.global_id),
            limit=10,
        )
    except Exception:
        items = []

    if not items:
        await message.answer(
            "🎯 Сейчас нет доступных заданий. Проверьте позже.",
            reply_markup=kb__main__menu(
                require_subscribe=bool(required_channel_id),
            ),
        )
        return

    lines = [
        t("tasks.submitted"),
        "Список (TOP-10):",
    ]
    for it in items:
        title = str(it.get("title") or "Task")
        bonus = d8(it.get("bonus_efhc") or 0)
        lines.append(f"• {title} — {bonus} EFHC")

    await message.answer(
        "\n".join(lines),
        reply_markup=kb__main__menu(
            require_subscribe=bool(required_channel_id),
        ),
    )
