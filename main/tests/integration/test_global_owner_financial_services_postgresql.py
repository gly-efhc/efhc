from __future__ import annotations

from decimal import Decimal

import pytest
from app.services.panels_service import activate_panel
from app.services.transactions_service import credit_user_from_bank
from app.services.withdraw_service import (
    cancel_withdraw,
    request_withdraw,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def _seed_control_bank_and_owner(
    db: AsyncSession,
    *,
    tg_id: int | None,
    main_balance: str = "0",
    bonus_balance: str = "0",
) -> int:
    global_id = int(
        (
            await db.execute(
                text(
                    "INSERT INTO efhc_core.users "
                    "(main_balance, bonus_balance) "
                    "VALUES (:main_balance, :bonus_balance) "
                    "RETURNING global_id"
                ),
                {
                    "main_balance": main_balance,
                    "bonus_balance": bonus_balance,
                },
            )
        ).scalar_one()
    )
    if tg_id is not None:
        await db.execute(
            text(
                "INSERT INTO efhc_core.user_identities ("
                "global_id, provider, provider_tenant, provider_subject, "
                "status, is_primary, is_verified, verified_at"
                ") VALUES ("
                ":global_id, 'telegram', 'default', :subject, "
                "'active', true, true, now()"
                ")"
            ),
            {"global_id": global_id, "subject": str(int(tg_id))},
        )
    return global_id



@pytest.mark.asyncio
async def test_canonical_global_owner_и_idempotency_ledger(
    db_session: AsyncSession,
) -> None:
    telegram_global_id = await _seed_control_bank_and_owner(
        db_session, tg_id=916410001
    )
    await db_session.commit()

    first = await credit_user_from_bank(
        db_session,
        global_id=telegram_global_id,
        amount=Decimal("5"),
        reason="cycle1641",
        idempotency_key="cycle1641-selector-equivalence",
    )
    second = await credit_user_from_bank(
        db_session,
        global_id=telegram_global_id,
        amount=Decimal("5"),
        reason="cycle1641",
        idempotency_key="cycle1641-selector-equivalence",
    )
    assert first.global_id == telegram_global_id
    assert second.detail == "idempotent"
    assert second.global_id == telegram_global_id
    count = int(
        (
            await db_session.execute(
                text(
                    "SELECT count(*) FROM efhc_core.efhc_transfers_log "
                    "WHERE idempotency_key = "
                    "'cycle1641-selector-equivalence'"
                )
            )
        ).scalar_one()
    )
    assert count == 1


@pytest.mark.asyncio
async def test_ton_only_credit_panel_withdraw_и_cancel(
    db_session: AsyncSession,
) -> None:
    global_id = await _seed_control_bank_and_owner(
        db_session,
        tg_id=None,
        main_balance="250",
    )
    await db_session.commit()

    credit = await credit_user_from_bank(
        db_session,
        global_id=global_id,
        amount=Decimal("10"),
        reason="cycle1641-ton-only",
        idempotency_key="cycle1641-ton-only-credit",
    )
    assert credit.tg_id is None
    assert credit.global_id == global_id
    transfer_owner = (
        await db_session.execute(
            text(
                "SELECT tg_id, global_id "
                "FROM efhc_core.efhc_transfers_log "
                "WHERE idempotency_key = 'cycle1641-ton-only-credit'"
            )
        )
    ).first()
    assert transfer_owner is not None
    assert transfer_owner[0] is None
    assert int(transfer_owner[1]) == global_id

    purchase = await activate_panel(
        db_session,
        global_id=global_id,
        qty=1,
        idempotency_key="cycle1642-ton-only-panel",
    )
    assert purchase.created_panel_ids
    panel_owner = (
        await db_session.execute(
            text(
                "SELECT global_id FROM efhc_core.panels "
                "WHERE id = :panel_id"
            ),
            {"panel_id": purchase.created_panel_ids[0]},
        )
    ).first()
    assert panel_owner is not None
    assert int(panel_owner[0]) == global_id

    request = await request_withdraw(
        db_session,
        global_id=global_id,
        amount=Decimal("10"),
        idempotency_key="cycle1642-ton-only-withdraw",
        external_address="EQ_TEST_WITHDRAW_DESTINATION",
    )
    assert request.global_id == global_id
    assert request.tg_id is None
    canceled = await cancel_withdraw(
        db_session,
        global_id=global_id,
        request_id=request.id,
    )
    assert canceled.status == "CANCELED"
    assert canceled.refund_done is True
