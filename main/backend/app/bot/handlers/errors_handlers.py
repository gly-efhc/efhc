# backend/app/bot/handlers/errors_handlers.py
# --------------------------------------------------------------------
# Назначение кода:
# Фолбэк-хэндлеры для неизвестных команд/сообщений.
#
# Канон:
# • Никаких денег. Только подсказка и меню.
# --------------------------------------------------------------------

from __future__ import annotations

from aiogram import Router
from aiogram.types import Message
from app.bot.keyboards import kb__main__menu
from app.bot.texts import t

router = Router()


@router.message()
async def fallback(
    message: Message,
    required_channel_id: int | None = None,
) -> None:
    """Асинхронная функция `fallback` выполняет операцию в контуре
    бота EFHC.

    Назначение: бизнес‑логика соответствующего модуля (см. имя функции
    и вызывающий код).

    Параметры:
    - `message` (Message): входной параметр.
    - `required_channel_id` (Optional[int]): входной параметр.

    Возвращает:
    - Значение типа/структуры: None.

    Инварианты и безопасность:
    - Повторный вызов не должен создавать дубли (идемпотентность
      достигается ключами/уникальными ограничениями).
    - Денежные значения в EFHC учитываются с точностью d8 и округлением
      вниз (ROUND_DOWN), если применимо по модулю.
    - Для операций, затрагивающих баланс/банк, изменения должны
      проходить через банковский сервис транзакций
      (transactions_service).
    """
    await message.answer(
        t("help"),
        reply_markup=kb__main__menu(
            require_subscribe=bool(required_channel_id),
        ),
    )
