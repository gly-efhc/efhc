"""Ограниченный historical read-through idempotency после global_id cutover.

Новые операции используют только ключи на основе canonical ``global_id``.
Legacy key разрешён лишь для защиты replay уже записанных переводов.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class HistoricalIdempotencyKey:
    """Выбранный canonical либо historical ключ replay."""

    selected: str
    canonical: str
    legacy: str | None
    matched_existing: bool


async def choose_idempotency_key_with_history(
    db: AsyncSession,
    *,
    canonical_key: str,
    legacy_key: str | None = None,
) -> HistoricalIdempotencyKey:
    """Найти исторический ключ или выбрать ключ текущего режима.

    Сначала выполняется read-through обоих допустимых ключей. Если
    операция уже существует, повтор использует именно найденный ключ.
    Любая новая операция всегда получает canonical key на основе
    ``global_id``. Legacy key разрешён только для historical
    read-through.
    """

    canonical = str(canonical_key).strip()
    legacy = str(legacy_key).strip() if legacy_key else None
    if not canonical:
        raise ValueError("canonical idempotency key пуст")
    if legacy == canonical:
        legacy = None

    row = (
        await db.execute(
            text(
                """
                SELECT idempotency_key
                FROM efhc_core.efhc_transfers_log
                WHERE idempotency_key = :canonical_key
                   OR (
                       CAST(:legacy_key AS TEXT) IS NOT NULL
                       AND idempotency_key = CAST(:legacy_key AS TEXT)
                   )
                ORDER BY
                    CASE
                        WHEN idempotency_key = :canonical_key THEN 0
                        ELSE 1
                    END
                LIMIT 1
                """
            ),
            {
                "canonical_key": canonical,
                "legacy_key": legacy,
            },
        )
    ).first()
    if row is not None:
        selected = str(row.idempotency_key)
        return HistoricalIdempotencyKey(
            selected=selected,
            canonical=canonical,
            legacy=legacy,
            matched_existing=True,
        )

    return HistoricalIdempotencyKey(
        selected=canonical,
        canonical=canonical,
        legacy=legacy,
        matched_existing=False,
    )


__all__ = [
    "HistoricalIdempotencyKey",
    "choose_idempotency_key_with_history",
]
