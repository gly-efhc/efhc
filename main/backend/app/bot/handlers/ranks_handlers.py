# backend/app/bot/handlers/ranks_handlers.py
# ----------------------------------------------------------------------
# Назначение кода:
# /ranks — рейтинг «Я + TOP-100» (по канону).
# ----------------------------------------------------------------------

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from app.bot.keyboards import kb__main__menu, kb_subscribe
from app.bot.texts import t
from app.core.logging_core import get_logger
from app.crud.user_crud import get_user_by_telegram_subject
from app.deps import d8
from app.services.ranks_service import get_user_rank_and_top
from sqlalchemy.ext.asyncio import AsyncSession

router = Router()
logger = get_logger(__name__)


def _rank_value(
    row: object,
    key: str,
    default: object = None,
) -> object:
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


async def _gate_subscribe(
    message: Message,
    required_channel_id: int | None,
    is_subscribed: bool,
    required_channel_username: str | None,
) -> bool:
    """Вспомогательная проверка подписки.

    Параметры:
    - `message` (Message): входной параметр.
    - `required_channel_id` (Optional[int]): входной параметр.
    - `is_subscribed` (bool): входной параметр.
    - `required_channel_username` (Optional[str]): входной параметр.

    Возвращает:
    - Значение типа/структуры: bool.

    Инварианты и безопасность:
    - Повторный вызов не должен создавать дубли (идемпотентность
      достигается ключами/уникальными ограничениями).
    - Денежные значения в EFHC учитываются с точностью d8 и
      округлением вниз (ROUND_DOWN), если применимо по модулю.
    - Для операций, затрагивающих баланс/банк, изменения проходят
      через банковский сервис транзакций (transactions_service).
    """
    if required_channel_id and not is_subscribed:
        channel = required_channel_username or str(required_channel_id)
        await message.answer(
            t("subscribe.required", channel=channel),
            reply_markup=kb_subscribe(required_channel_username),
        )
        return True
    return False


@router.message(Command("ranks"))
async def cmd_ranks(
    message: Message,
    db: AsyncSession,
    is_subscribed: bool = True,
    required_channel_username: str | None = None,
    required_channel_id: int | None = None,
) -> None:
    """Команда /ranks: «Я + TOP».

    Параметры:
    - `message` (Message): входной параметр.
    - `db` (AsyncSession): входной параметр.
    - `is_subscribed` (bool): входной параметр.
    - `required_channel_username` (Optional[str]): входной параметр.
    - `required_channel_id` (Optional[int]): входной параметр.

    Возвращает:
    - Значение типа/структуры: None.

    Инварианты и безопасность:
    - Повторный вызов не должен создавать дубли (идемпотентность
      достигается ключами/уникальными ограничениями).
    - Денежные значения в EFHC учитываются с точностью d8 и
      округлением вниз (ROUND_DOWN), если применимо по модулю.
    - Для операций, затрагивающих баланс/банк, изменения проходят
      через банковский сервис транзакций (transactions_service).
    """
    if not message.from_user:
        return
    tg_id = int(message.from_user.id)
    gate = await _gate_subscribe(
        message,
        required_channel_id,
        is_subscribed,
        required_channel_username,
    )
    if gate:
        return

    user = await get_user_by_telegram_subject(
        db,
        tg_id=tg_id,
    )
    if not user:
        await message.answer("Пользователь не найден. Нажмите /start")
        return

    try:
        user_global_id = getattr(user, "global_id", None)
        if user_global_id is None:
            raise ValueError("GLOBAL_ID_NOT_RESOLVED")
        me, top, meta = await get_user_rank_and_top(
            db,
            global_id=int(user_global_id),
            top_limit=10,
        )
        _ = meta
    except Exception:
        logger.exception("Failed to load ranks for bot user")
        me, top = None, []

    lines = []
    if me:
        lines.append(
            t(
                "ranks.me",
                rank=str(_rank_value(me, "rank", "?")),
                total_kwh=d8(_rank_value(me, "total_kwh", 0)),
            )
        )
    if top:
        lines.append(t("ranks.top.header", limit=str(len(top))))
        for row in top:
            lines.append(
                t(
                    "ranks.top.line",
                    rank=str(_rank_value(row, "rank", "?")),
                    username=str(
                        _rank_value(row, "username") or "user"
                    ),
                    total_kwh=d8(_rank_value(row, "total_kwh", 0)),
                )
            )

    if not lines:
        lines = ["🏆 Рейтинг пока недоступен. Попробуйте позже."]

    require_subscribe = bool(required_channel_id)
    await message.answer(
        "\n".join(lines),
        reply_markup=kb__main__menu(
            require_subscribe=require_subscribe
        ),
    )
