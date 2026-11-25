from __future__ import annotations

# ruff: noqa: E402,I001

import json
from decimal import Decimal

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
text = sqlalchemy.text

from app.services.admin.admin_bank_service import (  # noqa: E402
    BankService,
    BankUserTransferRequest,
)
from app.services.admin.admin_rbac import AdminRole, AdminUser  # noqa: E402

pytestmark = pytest.mark.asyncio


async def _insert_user(
    db,
    *,
    global_id: int,
    main: str = "0.00000000",
    bonus: str = "0.00000000",
) -> None:
    await db.execute(
        text(
            """
            INSERT INTO efhc_core.users (
                global_id, username, is_vip, is_active,
                main_balance, bonus_balance,
                total_generated_kwh, exchanged_kwh_total,
                created_at, updated_at
            ) VALUES (
                :global_id, :username, false, true,
                :main, :bonus,
                '0.00000000', '0.00000000',
                NOW(), NOW()
            )
            """
        ),
        {
            "global_id": global_id,
            "username": f"user_{global_id}",
            "main": main,
            "bonus": bonus,
        },
    )
    await db.commit()


async def _balances(db, global_id: int) -> tuple[Decimal, Decimal]:
    result = await db.execute(
        text(
            """
            SELECT main_balance, bonus_balance
            FROM efhc_core.users
            WHERE global_id = :global_id
            """
        ),
        {"global_id": global_id},
    )
    row = result.one()
    return Decimal(str(row[0])), Decimal(str(row[1]))


async def _bank_balance(db) -> Decimal:
    result = await db.execute(
        text(
            """
            SELECT balance
            FROM efhc_core.bank_balance
            WHERE key = 'EFHC_MAIN'
            """
        )
    )
    row = result.fetchone()
    return Decimal("0") if row is None else Decimal(str(row[0]))


async def _log_rows(db, idempotency_key: str):
    result = await db.execute(
        text(
            """
            SELECT balance_type, direction, reason,
                   idempotency_key, meta
            FROM efhc_core.efhc_transfers_log
            WHERE idempotency_key = :idk
            ORDER BY id
            """
        ),
        {"idk": idempotency_key},
    )
    return result.fetchall()


def _admin() -> AdminUser:
    return AdminUser(
        id=201,
        global_id=5_900_000_201,
        role=AdminRole.SUPERADMIN,
        is_active=True,
    )


async def test_admin_bonus_debit_accepts_meta_and_is_idempotent(
    db_session,
):
    global_id = 5_112_030_001
    await _insert_user(
        db_session,
        global_id=global_id,
        bonus="25.00000000",
    )
    admin = _admin()
    await _insert_user(db_session, global_id=admin.global_id)
    before_main, before_bonus = await _balances(db_session, global_id)
    before_bank = await _bank_balance(db_session)
    req = BankUserTransferRequest(
        global_id=f"{global_id:010d}",
        amount=Decimal("5.00000000"),
        direction="debit",
        balance_type="BONUS",
        reason="test_bonus_debit",
        idempotency_key="admin-bonus-debit-1",
    )

    result = await BankService.manual_bank_user_transfer(
        db_session,
        req=req,
        admin=admin,
    )

    assert result["ok"] is True
    after_main, after_bonus = await _balances(db_session, global_id)
    after_bank = await _bank_balance(db_session)
    assert after_main == before_main
    assert after_bonus == before_bonus - Decimal("5.00000000")
    assert after_bank == before_bank + Decimal("5.00000000")
    logs = await _log_rows(db_session, "admin-bonus-debit-1")
    assert len(logs) == 1
    row = logs[0]
    assert row.balance_type == "bonus"
    assert row.direction == "debit"
    assert row.reason == "admin_manual_bonus_debit"
    meta = json.loads(row.meta or "{}")
    assert meta["source"] == "admin_manual_bank_transfer"
    assert meta["admin_reason"] == "test_bonus_debit"

    replay = await BankService.manual_bank_user_transfer(
        db_session,
        req=req,
        admin=admin,
    )
    assert replay["ok"] is True
    assert await _log_rows(db_session, "admin-bonus-debit-1") == logs
    replay_balances = await _balances(db_session, global_id)
    assert replay_balances == (after_main, after_bonus)


async def test_admin_bonus_debit_insufficient_bonus_is_friendly(
    db_session,
):
    global_id = 5_112_040_001
    await _insert_user(
        db_session,
        global_id=global_id,
        bonus="1.00000000",
    )
    before = await _balances(db_session, global_id)
    req = BankUserTransferRequest(
        global_id=f"{global_id:010d}",
        amount=Decimal("5.00000000"),
        direction="debit",
        balance_type="BONUS",
        reason="test_bonus_debit_low",
        idempotency_key="admin-bonus-debit-low",
    )

    with pytest.raises(ValueError) as excinfo:
        await BankService.manual_bank_user_transfer(
            db_session,
            req=req,
            admin=_admin(),
        )

    assert "TypeError" not in str(excinfo.value)
    assert "Недостаточно средств" in str(excinfo.value)
    assert await _balances(db_session, global_id) == before
    assert await _log_rows(db_session, "admin-bonus-debit-low") == []
