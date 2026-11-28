"""Каноническая блокировка владельца финансовой мутации по ``global_id``."""

from __future__ import annotations

from dataclasses import dataclass

from app.identity.financial_owner import (
    FinancialReadOwnerError,
    _validate_global_id,
)
from app.identity.telegram_channel import (
    TelegramChannelResolutionError,
    resolve_verified_telegram_subject,
)
from app.models.user_models import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class FinancialWriteOwnerError(RuntimeError):
    """Владелец финансовой мутации не разрешён и не заблокирован."""


@dataclass(frozen=True, slots=True)
class FinancialWriteOwner:
    """Канонический владелец заблокированной финансовой мутации."""

    global_id: int
    provider_tg_id: int | None


async def resolve_and_lock_financial_write_owner(
    db: AsyncSession,
    *,
    global_id: int,
) -> FinancialWriteOwner:
    """Разрешить и заблокировать владельца только по ``global_id``.

    Telegram subject обязан быть разрешён на ingress-границе до вызова
    business service. Строка аккаунта блокируется ``FOR UPDATE`` в
    текущей транзакции; provider subject возвращается только как
    metadata для Telegram delivery и исторических внешних записей.
    """

    try:
        validated_global_id = _validate_global_id(global_id)
    except FinancialReadOwnerError as exc:
        raise FinancialWriteOwnerError(str(exc)) from exc

    statement = (
        select(User.global_id, User.is_active)
        .where(User.global_id == validated_global_id)
        .limit(1)
        .with_for_update()
    )
    user = (await db.execute(statement)).first()

    if user is None or user.global_id is None:
        raise FinancialWriteOwnerError("Account owner mapping не найден")
    if user.is_active is not True:
        raise FinancialWriteOwnerError("Account owner неактивен")

    try:
        provider_tg_id = await resolve_verified_telegram_subject(
            db, global_id=validated_global_id
        )
    except TelegramChannelResolutionError as exc:
        raise FinancialWriteOwnerError(str(exc)) from exc

    return FinancialWriteOwner(
        global_id=validated_global_id,
        provider_tg_id=provider_tg_id,
    )


__all__ = [
    "FinancialWriteOwner",
    "FinancialWriteOwnerError",
    "resolve_and_lock_financial_write_owner",
]
