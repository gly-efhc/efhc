"""Каноническое разрешение владельца нефинансового business-read по ``global_id``."""

from __future__ import annotations

from dataclasses import dataclass

from app.identity.telegram_channel import (
    TelegramChannelResolutionError,
    resolve_verified_telegram_subject,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

GLOBAL_ID_MIN = 1
GLOBAL_ID_MAX = 9_999_999_999


class NonFinancialReadOwnerError(RuntimeError):
    """Business owner не удалось разрешить из канонического ``global_id``."""


@dataclass(frozen=True, slots=True)
class NonFinancialReadOwner:
    """Канонический владелец и необязательные проверенные Telegram metadata."""

    global_id: int
    provider_tg_id: int | None


def _validate_global_id(value: int) -> int:
    global_id = int(value)
    if global_id < GLOBAL_ID_MIN or global_id > GLOBAL_ID_MAX:
        raise NonFinancialReadOwnerError("global_id вне диапазона")
    return global_id


async def resolve_nonfinancial_read_owner(
    db: AsyncSession,
    *,
    global_id: int,
) -> NonFinancialReadOwner:
    """Разрешить нефинансового business owner только из ``global_id``."""

    gid = _validate_global_id(global_id)
    exists = (
        await db.execute(
            text(
                """
                SELECT global_id
                  FROM efhc_core.users
                 WHERE global_id = :global_id
                   AND is_active IS TRUE
                 LIMIT 1
                """
            ),
            {"global_id": gid},
        )
    ).scalar_one_or_none()
    if exists is None:
        raise NonFinancialReadOwnerError("Account owner mapping не найден")

    try:
        provider_tg_id = await resolve_verified_telegram_subject(
            db, global_id=gid
        )
    except TelegramChannelResolutionError as exc:
        raise NonFinancialReadOwnerError(str(exc)) from exc

    return NonFinancialReadOwner(
        global_id=gid,
        provider_tg_id=provider_tg_id,
    )


__all__ = [
    "NonFinancialReadOwner",
    "NonFinancialReadOwnerError",
    "resolve_nonfinancial_read_owner",
]
