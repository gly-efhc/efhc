from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
text = sqlalchemy.text

pytestmark = pytest.mark.asyncio


async def _ensure_user(
    db_session,
    *,
    global_id: int,
    bonus_balance: str = "0.00000000",
) -> int:
    row = await db_session.execute(
        text(
            "\n".join(
                [
                    "INSERT INTO efhc_core.users (",
                    "  global_id, username, is_vip, is_active,",
                    "  main_balance, bonus_balance,",
                    "  total_generated_kwh, created_at, updated_at",
                    ") VALUES (",
                    "  :global_id, NULL, FALSE, TRUE,",
                    "  0, :bb,",
                    "  0, now(), now()",
                    ")",
                    "ON CONFLICT (global_id) DO UPDATE SET",
                    "  bonus_balance = excluded.bonus_balance,",
                    "  updated_at = now()",
                    "RETURNING global_id",
                ]
            )
        ),
        {
            "global_id": int(global_id),
            "bb": str(bonus_balance),
        },
    )
    return int(row.scalar_one())


async def _insert_panel(
    db_session,
    *,
    global_id: int,
    n: int,
) -> None:
    now = datetime.now(UTC)
    await db_session.execute(
        text(
            "\n".join(
                [
                    "INSERT INTO efhc_core.panels (",
                    "  global_id, is_active, is_archived, public_id,",
                    "  created_at, activated_at, expires_at,",
                    "  base_gen_per_sec, generated_kwh, updated_at",
                    ") VALUES (",
                    "  :global_id, TRUE, FALSE, :pid,",
                    "  :now, :now, :exp,",
                    "  0, 0, :now",
                    ")",
                ]
            )
        ),
        {
            "global_id": int(global_id),
            "pid": f"IDREF{n:06d}",
            "now": now,
            "exp": now + timedelta(days=180),
        },
    )


async def test_referral_level_bonus_auto_to_bonus_from_bank(
    db_session,
) -> None:
    from app.services.referral_service import (
        on_user_first_panel_activation,
    )

    inviter_global = await _ensure_user(
        db_session,
        global_id=305001,
    )

    for idx in range(1, 11):
        buyer_global = await _ensure_user(
            db_session,
            global_id=305099 + idx,
        )
        await db_session.execute(
            text(
                "\n".join(
                    [
                        "INSERT INTO efhc_core.referral_links (",
                        "  inviter_global_id, invitee_global_id,",
                        "  created_at, activated_at",
                        ") VALUES (",
                        "  :inviter_global_id, :invitee_global_id,",
                        "  :now, NULL",
                        ")",
                    ]
                )
            ),
            {
                "inviter_global_id": inviter_global,
                "invitee_global_id": buyer_global,
                "now": datetime.now(UTC),
            },
        )
        await _insert_panel(
            db_session,
            global_id=buyer_global,
            n=idx,
        )
        await on_user_first_panel_activation(
            db_session,
            buyer_global_id=buyer_global,
        )

    await db_session.commit()

    row = (
        await db_session.execute(
            text(
                "SELECT bonus_balance FROM efhc_core.users "
                "WHERE global_id = :global_id"
            ),
            {"global_id": inviter_global},
        )
    ).first()
    assert row is not None
    # Economic truth at Lvl 1: 10 × 0.1 EFHCb + 1 EFHCb = 2 EFHCb.
    assert Decimal(str(row[0])) == Decimal("2.00000000")

    bank = (
        await db_session.execute(
            text(
                "SELECT balance FROM efhc_core.bank_balance "
                "WHERE key = 'EFHC_MAIN'"
            )
        )
    ).first()
    assert bank is not None
    assert Decimal(str(bank[0])) == Decimal("-2.00000000")

    unit_count = (
        await db_session.execute(
            text(
                "SELECT COUNT(*) FROM efhc_core.efhc_transfers_log "
                "WHERE global_id = :global_id "
                "AND reason = 'referral_active_unit' "
                "AND balance_type = 'bonus' "
                "AND direction = 'credit'"
            ),
            {"global_id": inviter_global},
        )
    ).scalar()
    assert int(unit_count or 0) == 10

    level_count = (
        await db_session.execute(
            text(
                "SELECT COUNT(*) FROM efhc_core.efhc_transfers_log "
                "WHERE global_id = :global_id "
                "AND reason = 'referral_level_bonus' "
                "AND balance_type = 'bonus' "
                "AND direction = 'credit' "
                "AND idempotency_key = :idempotency_key"
            ),
            {
                "global_id": inviter_global,
                "idempotency_key": (
                    f"REF_LVL:G{inviter_global:010d}:L1"
                ),
            },
        )
    ).scalar()
    assert int(level_count or 0) == 1
