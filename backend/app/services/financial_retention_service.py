"""Исполняемый контур простой финансовой ретенции без partitioning.

Утверждённая владельцем модель:
- внешняя финансовая операция исполнима только при возрасте < 180 суток;
- история хранится до возраста 370 суток;
- массовая уборка истории начинается только при накоплении >= 400 суток;
- статус жизненного цикла не продлевает историю после границы хранения;
- удаление выполняется ограниченными батчами и не меняет BANK/balances;
- старый PENDING withdrawal сначала автоматически отменяется с каноническим
  возвратом холда, поэтому удаление истории не уничтожает денежное обязательство.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from app.services.financial_retention_foundation_service import (
    SIMPLE_FINANCIAL_HISTORY_DELETE_ORDER,
    build_simple_financial_retention_plan,
    require_utc,
    tx_hash_cleanup_cutoff,
)
from app.services.withdraw_service import cancel_withdraw
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_HISTORY_BATCH_SIZE: Final[int] = 1_000
DEFAULT_HISTORY_MAX_BATCHES_PER_TABLE: Final[int] = 50
DEFAULT_WITHDRAW_EXPIRY_BATCH_SIZE: Final[int] = 100
DEFAULT_WITHDRAW_EXPIRY_MAX_BATCHES: Final[int] = 10
DEFAULT_REPLAY_BATCH_SIZE: Final[int] = 1_000
DEFAULT_REPLAY_MAX_BATCHES: Final[int] = 50

_HISTORY_DELETE_SQL: Final[dict[str, str]] = {
    "efhc_transfers_log": """
        DELETE FROM efhc_core.efhc_transfers_log
         WHERE id IN (
            SELECT id
              FROM efhc_core.efhc_transfers_log
             WHERE created_at <= :delete_before
             ORDER BY created_at ASC, id ASC
             LIMIT :limit
             FOR UPDATE SKIP LOCKED
         )
        RETURNING id
    """,
    "payment_intents": """
        DELETE FROM efhc_core.payment_intents
         WHERE id IN (
            SELECT id
              FROM efhc_core.payment_intents
             WHERE created_at <= :delete_before
             ORDER BY created_at ASC, id ASC
             LIMIT :limit
             FOR UPDATE SKIP LOCKED
         )
        RETURNING id
    """,
    "shop_orders": """
        DELETE FROM efhc_core.shop_orders
         WHERE id IN (
            SELECT id
              FROM efhc_core.shop_orders
             WHERE created_at <= :delete_before
             ORDER BY created_at ASC, id ASC
             LIMIT :limit
             FOR UPDATE SKIP LOCKED
         )
        RETURNING id
    """,
    "withdraw_outcome_events": """
        DELETE FROM efhc_core.withdraw_outcome_events
         WHERE id IN (
            SELECT id
              FROM efhc_core.withdraw_outcome_events
             WHERE created_at <= :delete_before
             ORDER BY created_at ASC, id ASC
             LIMIT :limit
             FOR UPDATE SKIP LOCKED
         )
        RETURNING id
    """,
    "ton_inbox_logs": """
        DELETE FROM efhc_core.ton_inbox_logs
         WHERE id IN (
            SELECT id
              FROM efhc_core.ton_inbox_logs
             WHERE created_at <= :delete_before
             ORDER BY created_at ASC, id ASC
             LIMIT :limit
             FOR UPDATE SKIP LOCKED
         )
        RETURNING id
    """,
}


@dataclass(frozen=True, slots=True)
class RetentionRunStats:
    """Итог одного ограниченного запуска ретенции."""

    cleanup_triggered: bool
    expired_withdrawals: int
    history_deleted: dict[str, int]
    tx_hash_locks_deleted: int
    idempotency_keys_deleted: int


def _bounded_positive(value: int, *, maximum: int) -> int:
    normalized = int(value)
    if normalized < 1 or normalized > maximum:
        raise ValueError("RETENTION_BATCH_LIMIT_INVALID")
    return normalized


async def _oldest_financial_history_created_at(
    db: AsyncSession,
) -> datetime | None:
    """Найти серверное время самой старой строки области финансовой истории."""

    query = text(
        """
        SELECT MIN(oldest_at)
        FROM (
            SELECT MIN(created_at) AS oldest_at
              FROM efhc_core.efhc_transfers_log
            UNION ALL
            SELECT MIN(created_at) FROM efhc_core.payment_intents
            UNION ALL
            SELECT MIN(created_at) FROM efhc_core.shop_orders
            UNION ALL
            SELECT MIN(created_at) FROM efhc_core.withdraw_requests
            UNION ALL
            SELECT MIN(created_at) FROM efhc_core.withdraw_outcome_events
            UNION ALL
            SELECT MIN(created_at) FROM efhc_core.ton_inbox_logs
        ) AS retention_oldest
        """
    )
    value = (await db.execute(query)).scalar_one_or_none()
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise RuntimeError("RETENTION_OLDEST_TIMESTAMP_INVALID")
    return value.astimezone(UTC)


async def _stale_pending_withdrawals(
    db: AsyncSession,
    *,
    now: datetime,
    limit: int,
) -> list[tuple[int, int]]:
    """Вернуть старые PENDING-заявки на вывод для отмены и возврата холда."""

    cutoff = tx_hash_cleanup_cutoff(now)
    rows = (
        await db.execute(
            text(
                """
                SELECT id, global_id
                  FROM efhc_core.withdraw_requests
                 WHERE status = 'PENDING'
                   AND created_at <= :cutoff
                 ORDER BY created_at ASC, id ASC
                 LIMIT :limit
                """
            ),
            {"cutoff": cutoff, "limit": int(limit)},
        )
    ).all()
    return [(int(row[0]), int(row[1])) for row in rows]


async def expire_stale_pending_withdrawals(
    db: AsyncSession,
    *,
    now: datetime,
    batch_size: int = DEFAULT_WITHDRAW_EXPIRY_BATCH_SIZE,
    max_batches: int = DEFAULT_WITHDRAW_EXPIRY_MAX_BATCHES,
) -> int:
    """После 180 суток отменить PENDING withdrawal и вернуть его холд."""

    current = require_utc(now)
    size = _bounded_positive(batch_size, maximum=5_000)
    batches = _bounded_positive(max_batches, maximum=1_000)
    expired = 0
    for _ in range(batches):
        candidates = await _stale_pending_withdrawals(
            db,
            now=current,
            limit=size,
        )
        if not candidates:
            break
        progressed = 0
        for request_id, global_id in candidates:
            try:
                await cancel_withdraw(
                    db,
                    global_id=global_id,
                    request_id=request_id,
                    idempotency_key=(
                        f"retention-expire-withdraw:{request_id}"
                    ),
                )
            except (ValueError, RuntimeError) as exc:
                # Допустима только гонка, в которой другой процесс уже
                # перевёл заявку из PENDING. Денежную ошибку не скрываем.
                row = (
                    await db.execute(
                        text(
                            """
                            SELECT status
                              FROM efhc_core.withdraw_requests
                             WHERE id = :request_id
                            """
                        ),
                        {"request_id": request_id},
                    )
                ).first()
                if row is None or str(row[0]) != "PENDING":
                    await db.rollback()
                    continue
                raise RuntimeError(
                    "RETENTION_WITHDRAW_EXPIRY_FAILED"
                ) from exc
            expired += 1
            progressed += 1
        if progressed == 0:
            break
    return expired


async def _assert_no_unresolved_old_withdraw_hold(
    db: AsyncSession,
    *,
    delete_before: datetime,
) -> None:
    """Fail-closed: старый неразрешённый холд нельзя удалить как историю."""

    row = (
        await db.execute(
            text(
                """
                SELECT id
                  FROM efhc_core.withdraw_requests
                 WHERE created_at <= :delete_before
                   AND hold_done IS TRUE
                   AND refund_done IS FALSE
                   AND status <> 'PAID'
                 ORDER BY created_at ASC, id ASC
                 LIMIT 1
                """
            ),
            {"delete_before": delete_before},
        )
    ).first()
    if row is not None:
        raise RuntimeError("RETENTION_WITHDRAW_HOLD_UNRESOLVED")


async def _delete_history_batch(
    db: AsyncSession,
    *,
    table: str,
    delete_before: datetime,
    limit: int,
) -> int:
    """Удалить один ограниченный батч из заранее разрешённой таблицы."""

    if table == "withdraw_requests":
        statement = text(
            """
            DELETE FROM efhc_core.withdraw_requests AS parent
             WHERE parent.id IN (
                SELECT candidate.id
                  FROM efhc_core.withdraw_requests AS candidate
                 WHERE candidate.created_at <= :delete_before
                   AND NOT EXISTS (
                        SELECT 1
                          FROM efhc_core.withdraw_outcome_events AS child
                         WHERE child.withdraw_request_id = candidate.id
                           AND child.created_at > :delete_before
                   )
                 ORDER BY candidate.created_at ASC, candidate.id ASC
                 LIMIT :limit
                 FOR UPDATE OF candidate SKIP LOCKED
             )
            RETURNING parent.id
            """
        )
    else:
        sql = _HISTORY_DELETE_SQL.get(table)
        if sql is None:
            raise ValueError("RETENTION_TABLE_NOT_ALLOWED")
        statement = text(sql)
    rows = (
        await db.execute(
            statement,
            {"delete_before": delete_before, "limit": int(limit)},
        )
    ).all()
    await db.commit()
    return len(rows)


async def delete_financial_history_bounded(
    db: AsyncSession,
    *,
    now: datetime,
    batch_size: int = DEFAULT_HISTORY_BATCH_SIZE,
    max_batches_per_table: int = DEFAULT_HISTORY_MAX_BATCHES_PER_TABLE,
) -> tuple[bool, dict[str, int]]:
    """Удалить историю старше 370 суток только после trigger >=400 суток."""

    current = require_utc(now)
    size = _bounded_positive(batch_size, maximum=10_000)
    batches = _bounded_positive(max_batches_per_table, maximum=1_000)
    oldest = await _oldest_financial_history_created_at(db)
    plan = build_simple_financial_retention_plan(
        now=current,
        oldest_created_at=oldest,
    )
    deleted = {table: 0 for table in SIMPLE_FINANCIAL_HISTORY_DELETE_ORDER}
    if not plan.cleanup_required:
        return False, deleted

    await _assert_no_unresolved_old_withdraw_hold(
        db,
        delete_before=plan.delete_before,
    )
    for table in plan.tables_in_delete_order:
        for _ in range(batches):
            count = await _delete_history_batch(
                db,
                table=table,
                delete_before=plan.delete_before,
                limit=size,
            )
            deleted[table] += count
            if count < size:
                break
    return True, deleted


async def _delete_bounded_by_cutoff(
    db: AsyncSession,
    *,
    statement: str,
    cutoff: datetime,
    batch_size: int,
    max_batches: int,
    expires_before: datetime | None = None,
) -> int:
    """Выполнить ограниченную очистку служебных маркеров по возрасту."""

    size = _bounded_positive(batch_size, maximum=10_000)
    batches = _bounded_positive(max_batches, maximum=1_000)
    total = 0
    sql = text(statement)
    for _ in range(batches):
        params: dict[str, object] = {
            "cutoff": cutoff,
            "limit": size,
        }
        if expires_before is not None:
            params["expires_before"] = expires_before
        rows = (await db.execute(sql, params)).all()
        await db.commit()
        total += len(rows)
        if len(rows) < size:
            break
    return total


async def cleanup_replay_and_idempotency_bounded(
    db: AsyncSession,
    *,
    now: datetime,
    batch_size: int = DEFAULT_REPLAY_BATCH_SIZE,
    max_batches: int = DEFAULT_REPLAY_MAX_BATCHES,
) -> tuple[int, int]:
    """Очистить replay-маркеры по утверждённой 180-дневной политике."""

    cutoff = tx_hash_cleanup_cutoff(require_utc(now))
    tx_deleted = await _delete_bounded_by_cutoff(
        db,
        statement="""
            DELETE FROM efhc_core.tx_hash_locks
             WHERE id IN (
                SELECT id
                  FROM efhc_core.tx_hash_locks
                 WHERE trusted_operation_at <= :cutoff
                 ORDER BY trusted_operation_at ASC, id ASC
                 LIMIT :limit
                 FOR UPDATE SKIP LOCKED
             )
            RETURNING id
        """,
        cutoff=cutoff,
        batch_size=batch_size,
        max_batches=max_batches,
    )
    idem_deleted = await _delete_bounded_by_cutoff(
        db,
        statement="""
            DELETE FROM efhc_admin.idempotency_key
             WHERE id IN (
                SELECT id
                  FROM efhc_admin.idempotency_key
                 WHERE (
                       expires_at IS NOT NULL
                       AND expires_at <= :expires_before
                   ) OR (
                       scope = 'withdraw_approve'
                       AND created_at <= :cutoff
                   )
                 ORDER BY COALESCE(expires_at, created_at) ASC, id ASC
                 LIMIT :limit
                 FOR UPDATE SKIP LOCKED
             )
            RETURNING id
        """,
        cutoff=cutoff,
        batch_size=batch_size,
        max_batches=max_batches,
        expires_before=require_utc(now),
    )
    return tx_deleted, idem_deleted


async def run_simple_financial_retention(
    db: AsyncSession,
    *,
    now: datetime,
) -> RetentionRunStats:
    """Один ограниченный безопасный проход production-ретенции."""

    current = require_utc(now)
    expired = await expire_stale_pending_withdrawals(db, now=current)
    cleanup_triggered, history_deleted = await delete_financial_history_bounded(
        db,
        now=current,
    )
    tx_deleted, idem_deleted = await cleanup_replay_and_idempotency_bounded(
        db,
        now=current,
    )
    return RetentionRunStats(
        cleanup_triggered=cleanup_triggered,
        expired_withdrawals=expired,
        history_deleted=history_deleted,
        tx_hash_locks_deleted=tx_deleted,
        idempotency_keys_deleted=idem_deleted,
    )


__all__ = [
    "DEFAULT_HISTORY_BATCH_SIZE",
    "DEFAULT_HISTORY_MAX_BATCHES_PER_TABLE",
    "DEFAULT_REPLAY_BATCH_SIZE",
    "DEFAULT_REPLAY_MAX_BATCHES",
    "DEFAULT_WITHDRAW_EXPIRY_BATCH_SIZE",
    "DEFAULT_WITHDRAW_EXPIRY_MAX_BATCHES",
    "RetentionRunStats",
    "cleanup_replay_and_idempotency_bounded",
    "delete_financial_history_bounded",
    "expire_stale_pending_withdrawals",
    "run_simple_financial_retention",
]
