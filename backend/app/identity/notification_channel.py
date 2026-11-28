"""Разрешение Telegram-канала доставки из canonical account ownership."""

from __future__ import annotations

from dataclasses import dataclass

from app.identity.telegram_channel import (
    TelegramChannelResolutionError,
    resolve_verified_telegram_subject,
)
from sqlalchemy.ext.asyncio import AsyncSession


class NotificationChannelError(RuntimeError):
    """Канал доставки нельзя безопасно разрешить из canonical owner."""


@dataclass(frozen=True, slots=True)
class TelegramNotificationChannel:
    """Проверенная Telegram-цель доставки, разрешённая из ``global_id``."""

    global_id: int
    tg_id: int
    source: str = "verified_identity"


async def resolve_telegram_notification_channel(
    db: AsyncSession,
    *,
    global_id: int,
) -> TelegramNotificationChannel | None:
    """Разрешить Telegram только через активную verified provider mapping."""

    gid = int(global_id)
    try:
        tg_id = await resolve_verified_telegram_subject(db, global_id=gid)
    except TelegramChannelResolutionError as exc:
        raise NotificationChannelError(str(exc)) from exc
    if tg_id is None:
        return None
    return TelegramNotificationChannel(global_id=gid, tg_id=tg_id)


__all__ = [
    "NotificationChannelError",
    "TelegramNotificationChannel",
    "resolve_telegram_notification_channel",
]
