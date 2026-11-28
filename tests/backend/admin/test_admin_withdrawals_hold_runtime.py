from __future__ import annotations

# ruff: noqa: E402,I001

from decimal import Decimal

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
text = sqlalchemy.text

from app.services.admin.admin_rbac import AdminRole, AdminUser, EFHC_SUPERADMIN_GLOBAL_ID  # noqa: E402
from app.services.admin.admin_withdrawals_service import (  # noqa: E402
    WithdrawalApproveRequest,
    WithdrawalsService,
)

pytestmark = pytest.mark.asyncio


async def _insert_user(
    db,
    *,
    global_id: int,
    tg_id: int,
    main: str,
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
            "username": f"user_{tg_id}",
            "main": main,
            "bonus": bonus,
        },
    )
    await db.execute(
        text(
            """
            INSERT INTO efhc_core.user_identities (
                global_id, provider, provider_tenant, provider_subject,
                status, is_primary, is_verified, verified_at,
                created_at, updated_at
            ) VALUES (
                :global_id, 'telegram', 'default', :subject,
                'active', true, true, NOW(), NOW(), NOW()
            )
            ON CONFLICT DO NOTHING
            """
        ),
        {"global_id": global_id, "subject": str(int(tg_id))},
    )
    await db.commit()


async def _insert_withdraw(
    db,
    *,
    global_id: int,
    tg_id: int,
    amount: str,
    idempotency_key: str,
) -> int:
    result = await db.execute(
        text(
            """
            INSERT INTO efhc_core.withdraw_requests (
                global_id, tg_id, amount, status, idempotency_key,
                hold_done, refund_done, external_address,
                created_at, updated_at
            ) VALUES (
                :global_id, :tg_id, :amount, 'PENDING', :idk,
                false, false, :external_address,
                NOW(), NOW()
            )
            RETURNING id
            """
        ),
        {
            "global_id": global_id,
            "tg_id": tg_id,
            "amount": amount,
            "idk": idempotency_key,
            "external_address": (
                "UQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAJKZ"
            ),
        },
    )
    wid = int(result.scalar_one())
    await db.commit()
    return wid


async def _balances_pair(db, global_id: int) -> tuple[Decimal, Decimal]:
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


async def _withdraw_row(db, withdrawal_id: int):
    result = await db.execute(
        text(
            """
            SELECT status, hold_done, processing_idempotency_key,
                   error_message
            FROM efhc_core.withdraw_requests
            WHERE id = :wid
            """
        ),
        {"wid": withdrawal_id},
    )
    return result.one()


async def _transfer_count(db, *, idempotency_key: str) -> int:
    result = await db.execute(
        text(
            """
            SELECT COUNT(*)
            FROM efhc_core.efhc_transfers_log
            WHERE idempotency_key = :idk
            """
        ),
        {"idk": idempotency_key,
            "external_address": (
                "UQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAJKZ"
            ),
        },
    )
    return int(result.scalar_one())


def _admin() -> AdminUser:
    return AdminUser(
        id=101,
        global_id=EFHC_SUPERADMIN_GLOBAL_ID,
        tg_id=900001,
        role=AdminRole.SUPERADMIN,
        is_active=True,
    )


async def _insert_admin_actor(db) -> None:
    admin = _admin()
    await _insert_user(
        db,
        global_id=admin.global_id,
        tg_id=int(admin.tg_id or 0),
        main="0.00000000",
    )


def _approve_req(key: str) -> WithdrawalApproveRequest:
    # These tests exercise hold/balance finalization, not external wallet transport.
    # Wallet finalization now requires a prior payout reservation plus verified
    # on-chain tx evidence, so use the explicit manual path here.
    return WithdrawalApproveRequest(
        idempotency_key=key,
        confirmation_mode="manual",
        reason="runtime hold-repair test",
    )


async def test_проверка_withdraw_hold_repair_approve_no_typeerror(db_session):
    await _insert_admin_actor(db_session)
    global_id = 5_112_010_001
    tg_id = 511201
    await _insert_user(
        db_session,
        global_id=global_id,
        tg_id=tg_id,
        main="50.00000000",
        bonus="7.00000000",
    )
    wid = await _insert_withdraw(
        db_session,
        global_id=global_id,
        tg_id=tg_id,
        amount="10.00000000",
        idempotency_key="wd-hold-repair-1",
    )
    before_main, before_bonus = await _balances_pair(db_session, global_id)
    before_bank = await _bank_balance(db_session)

    result = await WithdrawalsService.approve_withdrawal(
        db_session,
        withdrawal_id=wid,
        req=_approve_req("approve-hold-repair-1"),
        admin=_admin(),
    )

    assert result["ok"] is True
    row = await _withdraw_row(db_session, wid)
    assert str(row.status).upper() == "PAID"
    assert bool(row.hold_done) is True
    assert row.processing_idempotency_key == "approve-hold-repair-1"
    assert await _transfer_count(
        db_session,
        idempotency_key="wd-hold-repair-1:hold",
    ) == 1
    after_main, after_bonus = await _balances_pair(db_session, global_id)
    after_bank = await _bank_balance(db_session)
    assert after_main == before_main - Decimal("10.00000000")
    assert after_bonus == before_bonus
    assert after_bank == before_bank + Decimal("10.00000000")

    replay = await WithdrawalsService.approve_withdrawal(
        db_session,
        withdrawal_id=wid,
        req=_approve_req("approve-hold-repair-1"),
        admin=_admin(),
    )
    assert replay["ok"] is True
    assert await _transfer_count(
        db_session,
        idempotency_key="wd-hold-repair-1:hold",
    ) == 1


async def test_проверка_withdraw_hold_repair_insufficient_balance_is_friendly(
    db_session,
):
    await _insert_admin_actor(db_session)
    global_id = 5_112_020_001
    tg_id = 511202
    await _insert_user(
        db_session,
        global_id=global_id,
        tg_id=tg_id,
        main="1.00000000",
        bonus="50.00000000",
    )
    wid = await _insert_withdraw(
        db_session,
        global_id=global_id,
        tg_id=tg_id,
        amount="10.00000000",
        idempotency_key="wd-hold-repair-low-main",
    )
    before = await _balances_pair(db_session, global_id)

    with pytest.raises(ValueError) as excinfo:
        await WithdrawalsService.approve_withdrawal(
            db_session,
            withdrawal_id=wid,
            req=_approve_req("approve-low-main"),
            admin=_admin(),
        )

    assert "TypeError" not in str(excinfo.value)
    assert "Недостаточно средств" in str(excinfo.value)
    row = await _withdraw_row(db_session, wid)
    assert str(row.status).upper() == "PENDING"
    assert bool(row.hold_done) is False
    assert row.error_message
    assert await _balances_pair(db_session, global_id) == before
