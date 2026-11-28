"""Ежедневный production-запуск простой финансовой ретенции."""

from __future__ import annotations

from typing import Any, Final

from app.core.database_core import db_session, get_engine
from app.core.logging_core import get_logger
from app.lib.time import utcnow
from app.services.financial_retention_service import (
    run_simple_financial_retention,
)
from sqlalchemy import text

logger = get_logger("efhc.scheduler.financial_retention")
_RETENTION_ADVISORY_LOCK: Final[int] = 1_774_1_779_370_400


async def run_once() -> dict[str, Any]:
    """Выполнить один сериализованный ограниченный проход ретенции."""

    engine = get_engine()
    async with engine.connect() as lock_conn:
        acquired = bool(
            (
                await lock_conn.execute(
                    text("SELECT pg_try_advisory_lock(:lock_key)"),
                    {"lock_key": _RETENTION_ADVISORY_LOCK},
                )
            ).scalar()
        )
        if not acquired:
            return {"skipped": True, "reason": "retention_lock_busy"}
        try:
            async with db_session() as db:
                stats = await run_simple_financial_retention(
                    db,
                    now=utcnow(),
                )
                return {
                    "cleanup_triggered": stats.cleanup_triggered,
                    "expired_withdrawals": stats.expired_withdrawals,
                    "history_deleted": stats.history_deleted,
                    "tx_hash_locks_deleted": stats.tx_hash_locks_deleted,
                    "idempotency_keys_deleted": (
                        stats.idempotency_keys_deleted
                    ),
                }
        finally:
            await lock_conn.execute(
                text("SELECT pg_advisory_unlock(:lock_key)"),
                {"lock_key": _RETENTION_ADVISORY_LOCK},
            )


__all__ = ["run_once"]
