# backend/app/crud/transactions_crud.py
# ======================================================================
# CRUD-слой для журналов:
# - efhc_transfers_log: фиксация движений EFHC (только запись/чтение).
# - ton_inbox_logs: входящие TON-транзакции вотчера (tx_hash UNIQUE).
# Денежные операции: только services/transactions_service.py.
# Пагинация: курсор по (id ASC), без OFFSET.
# ======================================================================

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from app.core.logging_core import get_logger
from app.deps import d8
from app.lib.time import utcnow
from app.models.transactions_models import EfhcTransferLog, TonInboxLog
from app.utils.cursor_codec import decode_cursor, encode_cursor
from sqlalchemy import Select, and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


# ======================================================================
# EFHC TRANSFERS LOG — insert/get/list/aggregate
# ======================================================================


async def insert_transfer_log_readthrough(
    db: AsyncSession,
    *,
    global_id: int,
    amount_efhc: Decimal,
    provider_tg_id: int | None = None,
    direction: str,
    balance_type: str,
    reason: str,
    idempotency_key: str,
) -> EfhcTransferLog:
    """Read-through insert по idempotency_key (UNIQUE)."""

    payload = {
        "global_id": int(global_id),
        "tg_id": (
            int(provider_tg_id)
            if provider_tg_id is not None
            else None
        ),
        "amount_efhc": d8(amount_efhc),
        "direction": str(direction),
        "balance_type": str(balance_type),
        "reason": str(reason),
        "idempotency_key": str(idempotency_key),
        "created_at": utcnow(),
    }

    stmt = (
        insert(EfhcTransferLog)
        .values(**payload)
        .returning(EfhcTransferLog)
    )

    try:
        async with db.begin_nested():
            res = await db.execute(stmt)
            return res.scalar_one()
    except IntegrityError:
        existing = await get_transfer_by_idempotency(
            db,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            return existing
        raise


async def get_transfer_by_idempotency(
    db: AsyncSession,
    *,
    idempotency_key: str,
) -> EfhcTransferLog | None:
    """Вернуть запись журнала EFHC по idempotency_key или None."""

    stmt = (
        select(EfhcTransferLog)
        .where(EfhcTransferLog.idempotency_key == str(idempotency_key))
        .limit(1)
    )
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def list_user_transfers_cursor(
    db: AsyncSession,
    *,
    global_id: int,
    limit: int = 50,
    next_cursor: str | None = None,
    direction: str | None = None,
    balance_type: str | None = None,
    reason: str | None = None,
) -> tuple[list[EfhcTransferLog], str | None]:
    """Список журнала EFHC по пользователю (id ASC), курсорный."""

    limit = max(1, min(int(limit), 200))

    after_id: int | None = None
    if next_cursor:
        payload = decode_cursor(next_cursor)
        raw = payload.get("after_id")
        if raw is not None:
            after_id = int(raw or 0)

    stmt: Select = select(EfhcTransferLog).where(
        EfhcTransferLog.global_id == int(global_id)
    )

    if direction:
        stmt = stmt.where(EfhcTransferLog.direction == str(direction))

    if balance_type:
        bt = str(balance_type)
        stmt = stmt.where(EfhcTransferLog.balance_type == bt)

    if reason:
        stmt = stmt.where(EfhcTransferLog.reason == str(reason))

    if after_id is not None:
        stmt = stmt.where(EfhcTransferLog.id > after_id)

    stmt = stmt.order_by(EfhcTransferLog.id.asc()).limit(limit)

    rows = (await db.execute(stmt)).scalars().all()

    nxt = None
    if rows and len(rows) == limit:
        nxt = encode_cursor({"after_id": int(rows[-1].id)})

    return list(rows), nxt


async def list_user_transfers_desc_cursor(
    db: AsyncSession,
    *,
    global_id: int,
    limit: int = 50,
    next_cursor: str | None = None,
    direction: str | None = None,
    balance_type: str | None = None,
    reason: str | None = None,
) -> tuple[list[EfhcTransferLog], str | None]:
    """Список журнала EFHC по пользователю (id DESC), курсорный."""

    limit = max(1, min(int(limit), 200))

    before_id: int | None = None
    if next_cursor:
        payload = decode_cursor(next_cursor)
        raw = payload.get("before_id")
        if raw is not None:
            before_id = int(raw or 0)

    stmt: Select = select(EfhcTransferLog).where(
        EfhcTransferLog.global_id == int(global_id)
    )

    if direction:
        stmt = stmt.where(EfhcTransferLog.direction == str(direction))

    if balance_type:
        bt = str(balance_type)
        stmt = stmt.where(EfhcTransferLog.balance_type == bt)

    if reason:
        stmt = stmt.where(EfhcTransferLog.reason == str(reason))

    if before_id is not None:
        stmt = stmt.where(EfhcTransferLog.id < before_id)

    stmt = stmt.order_by(EfhcTransferLog.id.desc()).limit(limit)

    rows = (await db.execute(stmt)).scalars().all()

    nxt = None
    if rows and len(rows) == limit:
        nxt = encode_cursor({"before_id": int(rows[-1].id)})

    return list(rows), nxt


async def aggregates_for_user(
    db: AsyncSession,
    *,
    global_id: int,
) -> tuple[Decimal, Decimal, Decimal]:
    """(Σ credit, Σ debit, credit - debit) по журналу EFHC."""

    base = EfhcTransferLog.global_id == int(global_id)

    q_credit = select(
        func.coalesce(func.sum(EfhcTransferLog.amount_efhc), 0)
    ).where(and_(base, EfhcTransferLog.direction == "credit"))

    q_debit = select(
        func.coalesce(func.sum(EfhcTransferLog.amount_efhc), 0)
    ).where(and_(base, EfhcTransferLog.direction == "debit"))

    credit_val = (await db.execute(q_credit)).scalar_one() or 0
    debit_val = (await db.execute(q_debit)).scalar_one() or 0

    credit = d8(Decimal(credit_val))
    debit = d8(Decimal(debit_val))
    net = d8(credit - debit)

    return credit, debit, net


# ======================================================================
# TON INBOX LOGS — insert/get/list/update (watcher helper)
# ======================================================================


async def upsert_ton_inbox_readthrough(
    db: AsyncSession,
    *,
    tx_hash: str,
    from_address: str,
    to_address: str,
    amount: Decimal,
    memo: str | None,
    initial_status: str = "received",
) -> TonInboxLog:
    """Read-through insert по tx_hash (UNIQUE)."""

    now = utcnow()

    payload = {
        "tx_hash": str(tx_hash),
        "from_address": str(from_address),
        "to_address": str(to_address),
        "amount": d8(amount),
        "memo": memo,
        "status": str(initial_status),
        "retries_count": 0,
        "next_retry_at": None,
        "last_error": None,
        "processed_at": None,
        "created_at": now,
        "updated_at": now,
    }

    stmt = (
        insert(TonInboxLog)
        .values(**payload)
        .on_conflict_do_nothing(index_elements=["tx_hash"])
        .returning(TonInboxLog)
    )

    res = await db.execute(stmt)
    row = res.scalar_one_or_none()
    if row:
        return row

    return await get_ton_inbox_by_hash(db, tx_hash=tx_hash)


async def get_ton_inbox_by_hash(
    db: AsyncSession,
    *,
    tx_hash: str,
) -> TonInboxLog | None:
    """Вернуть запись TON по tx_hash или None."""

    stmt = (
        select(TonInboxLog)
        .where(TonInboxLog.tx_hash == str(tx_hash))
        .limit(1)
    )
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def set_ton_status(
    db: AsyncSession,
    *,
    tx_hash: str,
    status: str,
    next_retry_at: datetime | None = None,
    last_error: str | None = None,
    processed_at: datetime | None = None,
    retries_inc: bool = False,
) -> TonInboxLog | None:
    """Обновить статус TON-лога (вотчер)."""

    row = await get_ton_inbox_by_hash(db, tx_hash=tx_hash)
    if not row:
        return None

    row.status = str(status)
    row.updated_at = utcnow()

    if last_error is not None:
        row.last_error = last_error[:1024]

    row.next_retry_at = next_retry_at

    if processed_at is not None:
        row.processed_at = processed_at

    if retries_inc:
        row.retries_count = int(row.retries_count or 0) + 1

    await db.flush()
    return row


async def list_ton_pending_cursor(
    db: AsyncSession,
    *,
    limit: int = 200,
    next_cursor: str | None = None,
    not_in_statuses: Sequence[str] | None = None,
) -> tuple[list[TonInboxLog], str | None]:
    """Список TON для обработки (курсорно)."""

    limit = max(1, min(int(limit), 500))

    after_id: int | None = None
    if next_cursor:
        payload = decode_cursor(next_cursor)
        raw = payload.get("after_id")
        if raw is not None:
            after_id = int(raw or 0)

    now = utcnow()

    stmt: Select = select(TonInboxLog)

    if not_in_statuses:
        statuses = list(map(str, not_in_statuses))
        stmt = stmt.where(TonInboxLog.status.not_in(statuses))

    stmt = stmt.where(
        (TonInboxLog.next_retry_at.is_(None))
        | (TonInboxLog.next_retry_at <= now)
    )

    if after_id is not None:
        stmt = stmt.where(TonInboxLog.id > after_id)

    stmt = stmt.order_by(TonInboxLog.id.asc()).limit(limit)

    rows = (await db.execute(stmt)).scalars().all()

    nxt = None
    if rows and len(rows) == limit:
        nxt = encode_cursor({"after_id": int(rows[-1].id)})

    return list(rows), nxt


async def list_ton_range_cursor(
    db: AsyncSession,
    *,
    since_created_at: datetime | None = None,
    until_created_at: datetime | None = None,
    limit: int = 200,
    next_cursor: str | None = None,
) -> tuple[list[TonInboxLog], str | None]:
    """Админская выборка по created_at + курсор (id ASC)."""

    limit = max(1, min(int(limit), 500))

    after_id: int | None = None
    if next_cursor:
        payload = decode_cursor(next_cursor)
        raw = payload.get("after_id")
        if raw is not None:
            after_id = int(raw or 0)

    stmt: Select = select(TonInboxLog)

    if since_created_at is not None:
        stmt = stmt.where(TonInboxLog.created_at >= since_created_at)

    if until_created_at is not None:
        stmt = stmt.where(TonInboxLog.created_at < until_created_at)

    if after_id is not None:
        stmt = stmt.where(TonInboxLog.id > after_id)

    stmt = stmt.order_by(TonInboxLog.id.asc()).limit(limit)

    rows = (await db.execute(stmt)).scalars().all()

    nxt = None
    if rows and len(rows) == limit:
        nxt = encode_cursor({"after_id": int(rows[-1].id)})

    return list(rows), nxt


# ======================================================================
# Метрики/агрегаты для отчётности
# ======================================================================


async def ton_retry_stats(db: AsyncSession) -> tuple[int, int, int]:
    """(total, with_errors, waiting_retry) по ton_inbox_logs."""

    now = utcnow()

    total_stmt = select(func.count(TonInboxLog.id))
    total = (await db.execute(total_stmt)).scalar_one() or 0

    err_stmt = select(func.count(TonInboxLog.id)).where(
        TonInboxLog.status.ilike("error_%")
    )
    with_errors = (await db.execute(err_stmt)).scalar_one() or 0

    wait_stmt = select(func.count(TonInboxLog.id)).where(
        and_(
            TonInboxLog.next_retry_at.is_not(None),
            TonInboxLog.next_retry_at > now,
        )
    )
    waiting_retry = (await db.execute(wait_stmt)).scalar_one() or 0

    return int(total), int(with_errors), int(waiting_retry)
