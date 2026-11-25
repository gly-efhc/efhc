"""PostgreSQL proof 180-дневного replay/idempotency barrier.

Этот набор тестов проверяет не только чистую функцию времени, а реальный
``tx_hash_locks`` settlement contour: истёкшая/аномальная операция обязана
останавливаться ДО обращения к replay-table, а допустимая операция получает
ровно один глобальный claim.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from app.identity.types import global_id_from_database
from app.lib.time import utcnow
from app.services.financial_execution_window import (
    FinancialExecutionWindowError,
)
from app.services.shop_payment_tx_hash_lock_service import (
    claim_tx_hash_settlement,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _new_global_id(db: AsyncSession) -> str:
    result = await db.execute(
        text(
            "INSERT INTO efhc_core.users DEFAULT VALUES "
            "RETURNING global_id"
        )
    )
    global_id = int(result.scalar_one())
    await db.commit()
    return str(global_id_from_database(global_id))


async def _lock_count(db: AsyncSession, tx_hash: str) -> int:
    result = await db.execute(
        text(
            "SELECT count(*) FROM efhc_core.tx_hash_locks "
            "WHERE tx_hash = :tx_hash"
        ),
        {"tx_hash": tx_hash},
    )
    return int(result.scalar_one())


@pytest.mark.asyncio
async def test_истёкшая_операция_не_создаёт_replay_claim(
    db_session: AsyncSession,
) -> None:
    global_id = await _new_global_id(db_session)
    now = utcnow()
    trusted = now - timedelta(days=180, seconds=1)

    with pytest.raises(FinancialExecutionWindowError):
        await claim_tx_hash_settlement(
            db_session,
            tx_hash="barrier-expired-180d",
            purpose="deposit_efhc",
            global_id=global_id,
            trusted_operation_at=trusted,
            server_first_seen_at=trusted + timedelta(minutes=1),
        )

    assert await _lock_count(db_session, "barrier-expired-180d") == 0


@pytest.mark.asyncio
async def test_новый_first_seen_не_омолаживает_старую_операцию(
    db_session: AsyncSession,
) -> None:
    global_id = await _new_global_id(db_session)
    now = utcnow()
    trusted = now - timedelta(days=181)

    with pytest.raises(FinancialExecutionWindowError):
        await claim_tx_hash_settlement(
            db_session,
            tx_hash="barrier-no-rejuvenation",
            purpose="deposit_efhc",
            global_id=global_id,
            trusted_operation_at=trusted,
            server_first_seen_at=now - timedelta(seconds=1),
        )

    assert await _lock_count(db_session, "barrier-no-rejuvenation") == 0


@pytest.mark.asyncio
async def test_аномальное_будущее_время_не_создаёт_replay_claim(
    db_session: AsyncSession,
) -> None:
    global_id = await _new_global_id(db_session)
    now = utcnow()

    with pytest.raises(FinancialExecutionWindowError):
        await claim_tx_hash_settlement(
            db_session,
            tx_hash="barrier-future",
            purpose="deposit_efhc",
            global_id=global_id,
            trusted_operation_at=now + timedelta(minutes=1),
            server_first_seen_at=now,
        )

    assert await _lock_count(db_session, "barrier-future") == 0


@pytest.mark.asyncio
async def test_допустимый_tx_hash_получает_один_глобальный_claim(
    db_session: AsyncSession,
) -> None:
    global_id = await _new_global_id(db_session)
    trusted = utcnow() - timedelta(days=10)
    first_seen = trusted + timedelta(minutes=1)

    first = await claim_tx_hash_settlement(
        db_session,
        tx_hash="barrier-single-claim",
        purpose="deposit_efhc",
        global_id=global_id,
        trusted_operation_at=trusted,
        server_first_seen_at=first_seen,
    )
    assert first.acquired is True
    assert first.same_claim is False

    same = await claim_tx_hash_settlement(
        db_session,
        tx_hash="barrier-single-claim",
        purpose="deposit_efhc",
        global_id=global_id,
        trusted_operation_at=trusted,
        server_first_seen_at=first_seen,
    )
    assert same.acquired is False
    assert same.same_claim is True
    assert same.can_continue is True

    conflicting = await claim_tx_hash_settlement(
        db_session,
        tx_hash="barrier-single-claim",
        purpose="shop_order",
        global_id=global_id,
        trusted_operation_at=trusted,
        server_first_seen_at=first_seen,
    )
    assert conflicting.acquired is False
    assert conflicting.same_claim is False
    assert conflicting.can_continue is False
    assert await _lock_count(db_session, "barrier-single-claim") == 1


@pytest.mark.asyncio
async def test_отсутствующий_trusted_time_не_создаёт_replay_claim(
    db_session: AsyncSession,
) -> None:
    global_id = await _new_global_id(db_session)
    now = utcnow()

    with pytest.raises(FinancialExecutionWindowError):
        await claim_tx_hash_settlement(
            db_session,
            tx_hash="barrier-missing-trusted",
            purpose="deposit_efhc",
            global_id=global_id,
            trusted_operation_at=None,
            server_first_seen_at=now,
        )

    assert await _lock_count(db_session, "barrier-missing-trusted") == 0


@pytest.mark.asyncio
async def test_отсутствующий_first_seen_не_создаёт_replay_claim(
    db_session: AsyncSession,
) -> None:
    global_id = await _new_global_id(db_session)
    trusted = utcnow() - timedelta(minutes=1)

    with pytest.raises(FinancialExecutionWindowError):
        await claim_tx_hash_settlement(
            db_session,
            tx_hash="barrier-missing-first-seen",
            purpose="deposit_efhc",
            global_id=global_id,
            trusted_operation_at=trusted,
            server_first_seen_at=None,
        )

    assert await _lock_count(db_session, "barrier-missing-first-seen") == 0


@pytest.mark.asyncio
async def test_first_seen_раньше_trusted_не_создаёт_replay_claim(
    db_session: AsyncSession,
) -> None:
    global_id = await _new_global_id(db_session)
    trusted = utcnow() - timedelta(minutes=1)

    with pytest.raises(FinancialExecutionWindowError):
        await claim_tx_hash_settlement(
            db_session,
            tx_hash="barrier-inverted-evidence",
            purpose="deposit_efhc",
            global_id=global_id,
            trusted_operation_at=trusted,
            server_first_seen_at=trusted - timedelta(microseconds=1),
        )

    assert await _lock_count(db_session, "barrier-inverted-evidence") == 0


@pytest.mark.asyncio
async def test_future_first_seen_не_создаёт_replay_claim(
    db_session: AsyncSession,
) -> None:
    global_id = await _new_global_id(db_session)
    now = utcnow()

    with pytest.raises(FinancialExecutionWindowError):
        await claim_tx_hash_settlement(
            db_session,
            tx_hash="barrier-future-first-seen",
            purpose="deposit_efhc",
            global_id=global_id,
            trusted_operation_at=now - timedelta(minutes=1),
            server_first_seen_at=now + timedelta(minutes=1),
        )

    assert await _lock_count(db_session, "barrier-future-first-seen") == 0


@pytest.mark.asyncio
async def test_replay_с_изменённым_time_evidence_не_является_same_claim(
    db_session: AsyncSession,
) -> None:
    global_id = await _new_global_id(db_session)
    trusted = utcnow() - timedelta(days=10)
    first_seen = trusted + timedelta(minutes=1)

    first = await claim_tx_hash_settlement(
        db_session,
        tx_hash="barrier-evidence-bound-claim",
        purpose="deposit_efhc",
        global_id=global_id,
        trusted_operation_at=trusted,
        server_first_seen_at=first_seen,
    )
    assert first.acquired is True

    changed = await claim_tx_hash_settlement(
        db_session,
        tx_hash="barrier-evidence-bound-claim",
        purpose="deposit_efhc",
        global_id=global_id,
        trusted_operation_at=trusted,
        server_first_seen_at=first_seen + timedelta(microseconds=1),
    )
    assert changed.acquired is False
    assert changed.same_claim is False
    assert changed.can_continue is False
    assert await _lock_count(db_session, "barrier-evidence-bound-claim") == 1
