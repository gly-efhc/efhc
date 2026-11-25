from __future__ import annotations

# ruff: noqa: E402,I001

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
text = sqlalchemy.text

from app.services.admin.admin_withdrawals_service import (  # noqa: E402
    WithdrawalFilters,
    WithdrawalsService,
)

pytestmark = pytest.mark.asyncio


async def _insert_user(
    db,
    *,
    global_id: int,
    is_vip: bool = False,
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
                :global_id, :username, :is_vip, true,
                '100.00000000', '0.00000000',
                '0.00000000', '0.00000000',
                NOW(), NOW()
            )
            """
        ),
        {
            "global_id": global_id,
            "username": f"user_{global_id}",
            "is_vip": bool(is_vip),
        },
    )
    await db.commit()


async def _insert_withdraw(
    db,
    *,
    global_id: int,
    amount: str,
    status: str = "PENDING",
    key: str,
) -> int:
    result = await db.execute(
        text(
            """
            INSERT INTO efhc_core.withdraw_requests (
                global_id, amount, status, idempotency_key,
                hold_done, refund_done, external_address,
                created_at, updated_at
            ) VALUES (
                :global_id, :amount, :status, :idk,
                false, false, :external_address,
                NOW(), NOW()
            )
            RETURNING id
            """
        ),
        {
            "global_id": global_id,
            "amount": amount,
            "status": status,
            "idk": key,
            "external_address": (
                "UQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAJKZ"
            ),
        },
    )
    await db.commit()
    return int(result.scalar_one())


async def _bonus_awards_absent(db) -> bool:
    result = await db.execute(
        text(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'efhc_admin'
              AND table_name = 'bonus_awards'
            LIMIT 1
            """
        )
    )
    return result.fetchone() is None


async def test_list_returns_pending_without_bonus_awards(
    db_session,
):
    global_id = 5_230_100_001
    await _insert_user(
        db_session, global_id=global_id
    )
    await _insert_withdraw(
        db_session,
        global_id=global_id,
        amount="7.00000000",
        key="wd-list-runtime-1",
    )
    assert await _bonus_awards_absent(db_session)

    rows = await WithdrawalsService.list_withdrawals(
        db_session,
        WithdrawalFilters(status="PENDING"),
    )

    assert len(rows) == 1
    assert rows[0].global_id == f"{global_id:010d}"
    assert rows[0].status == "PENDING"


async def test_status_filter_returns_only_pending(db_session):
    global_id = 5_230_100_002
    await _insert_user(
        db_session, global_id=global_id
    )
    for status in ["PENDING", "PAID", "REJECTED", "CANCELED"]:
        await _insert_withdraw(
            db_session,
            global_id=global_id,
            amount="1.00000000",
            status=status,
            key=f"wd-list-status-{status.lower()}",
        )

    rows = await WithdrawalsService.list_withdrawals(
        db_session,
        WithdrawalFilters(status="PENDING"),
    )

    assert [row.status for row in rows] == ["PENDING"]


async def test_global_id_filter_returns_only_requested_user(db_session):
    first_global_id = 5_230_100_003
    second_global_id = 5_230_100_004
    await _insert_user(
        db_session, global_id=first_global_id
    )
    await _insert_user(
        db_session, global_id=second_global_id
    )
    await _insert_withdraw(
        db_session,
        global_id=first_global_id,
        amount="1.00000000",
        key="wd-list-global-1",
    )
    await _insert_withdraw(
        db_session,
        global_id=second_global_id,
        amount="2.00000000",
        key="wd-list-global-2",
    )

    rows = await WithdrawalsService.list_withdrawals(
        db_session,
        WithdrawalFilters(global_id=f"{first_global_id:010d}"),
    )

    assert len(rows) == 1
    assert rows[0].global_id == f"{first_global_id:010d}"


async def test_vip_only_filter_returns_only_vip_user(db_session):
    vip_global_id = 5_230_100_005
    regular_global_id = 5_230_100_006
    await _insert_user(
        db_session,
        global_id=vip_global_id,
        is_vip=True,
    )
    await _insert_user(
        db_session,
        global_id=regular_global_id,
        is_vip=False,
    )
    await _insert_withdraw(
        db_session,
        global_id=vip_global_id,
        amount="1.00000000",
        key="wd-list-vip-1",
    )
    await _insert_withdraw(
        db_session,
        global_id=regular_global_id,
        amount="2.00000000",
        key="wd-list-vip-2",
    )

    rows = await WithdrawalsService.list_withdrawals(
        db_session,
        WithdrawalFilters(vip_only=True),
    )

    assert len(rows) == 1
    assert rows[0].global_id == f"{vip_global_id:010d}"
    assert rows[0].is_vip is True


async def test_pagination_and_sort_do_not_break(db_session):
    global_id = 5_230_100_007
    await _insert_user(
        db_session, global_id=global_id
    )
    first = await _insert_withdraw(
        db_session,
        global_id=global_id,
        amount="1.00000000",
        key="wd-list-sort-1",
    )
    second = await _insert_withdraw(
        db_session,
        global_id=global_id,
        amount="2.00000000",
        key="wd-list-sort-2",
    )

    desc_rows = await WithdrawalsService.list_withdrawals(
        db_session,
        WithdrawalFilters(limit=1, sort_desc=True),
    )
    asc_rows = await WithdrawalsService.list_withdrawals(
        db_session,
        WithdrawalFilters(limit=1, sort_desc=False),
    )

    assert len(desc_rows) == 1
    assert desc_rows[0].id == second
    assert asc_rows[0].id == first
