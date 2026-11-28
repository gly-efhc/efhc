"""Канонический поиск Telegram delivery-subject по ``global_id``.

Telegram остаётся границей провайдера и доставки. Модуль никогда не определяет
business owner через ``tg_id`` и не использует fallback на ``users.tg_id``.
"""

from __future__ import annotations

from app.identity.provider_registry import AuthProvider
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class TelegramChannelResolutionError(RuntimeError):
    """Проверенный Telegram-канал доставки нельзя определить однозначно."""


def _positive_tg_id(value: str | int | None) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    raw = str(value).strip()
    if not raw.isascii() or not raw.isdecimal():
        return None
    parsed = int(raw)
    return parsed if parsed > 0 else None


async def resolve_verified_telegram_subject(
    db: AsyncSession,
    *,
    global_id: int,
) -> int | None:
    """Вернуть единственный проверенный активный Telegram subject для ``global_id``.

    Отсутствие Telegram identity является допустимым provider-neutral состоянием
    и возвращает ``None``. Несколько разных активных проверенных subjects
    обрабатываются fail-closed.
    """

    gid = int(global_id)
    if gid < 1 or gid > 9_999_999_999:
        raise TelegramChannelResolutionError("global_id вне диапазона")

    rows = (
        await db.execute(
            text(
                """
                SELECT provider_subject
                  FROM efhc_core.user_identities
                 WHERE global_id = :global_id
                   AND provider = :provider
                   AND provider_tenant = 'default'
                   AND status = 'active'
                   AND is_verified = TRUE
                 ORDER BY is_primary DESC, id ASC
                """
            ),
            {
                "global_id": gid,
                "provider": AuthProvider.TELEGRAM.value,
            },
        )
    ).all()

    subjects = {
        subject
        for row in rows
        if (subject := _positive_tg_id(row.provider_subject)) is not None
    }
    if len(subjects) > 1:
        raise TelegramChannelResolutionError(
            "Несколько verified Telegram subjects для одного global_id"
        )
    return next(iter(subjects), None)


__all__ = [
    "TelegramChannelResolutionError",
    "resolve_verified_telegram_subject",
]
