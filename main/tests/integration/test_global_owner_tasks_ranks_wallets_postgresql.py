"""PostgreSQL qualification canonical owner цикла 1644."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.services.ranks_service import (
    get_leaderboard_page,
    get_user_rank_and_top,
    rebuild_rank_snapshot,
)
from app.services.tasks_service import (
    complete_task,
    confirm_ad_view_and_credit,
    list_available_tasks,
    list_task_bonus_log,
)
from app.services.wallets_service import (
    has_active_wallet,
    list_wallets,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def _seed_owner(
    db: AsyncSession,
    *,
    tg_id: int | None,
    total_kwh: str,
) -> int:
    global_id = int(
        (
            await db.execute(
                text(
                    """
                    INSERT INTO efhc_core.users (
                        is_active,
                        total_generated_kwh
                    ) VALUES (
                        TRUE,
                        :total_kwh
                    )
                    RETURNING global_id
                    """
                ),
                {"total_kwh": total_kwh},
            )
        ).scalar_one()
    )
    if tg_id is not None:
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
                """
            ),
            {"global_id": global_id, "subject": str(int(tg_id))},
        )
    return global_id


@pytest.mark.asyncio
async def test_ton_only_задачи_кошельки_и_рейтинг_используют_global_owner(
    db_session: AsyncSession,
) -> None:
    ton_global_id = await _seed_owner(
        db_session,
        tg_id=None,
        total_kwh="12.00000000",
    )
    telegram_global_id = await _seed_owner(
        db_session,
        tg_id=916440001,
        total_kwh="7.00000000",
    )
    await db_session.execute(
        text(
            """
            INSERT INTO efhc_core.tasks (
                code,
                title,
                type,
                active,
                bonus_efhc,
                limit_per_user,
                performed_count
            ) VALUES (
                'cycle1644_ad',
                'Cycle 1644 ad',
                'watch_ad',
                TRUE,
                '1.25000000',
                1,
                0
            )
            ON CONFLICT (code) DO NOTHING
            """
        )
    )
    await db_session.execute(
        text(
            """
            INSERT INTO efhc_core.wallet_bindings (
                global_id,
                wallet_address,
                is_primary,
                is_active,
                proof_verified
            ) VALUES (
                :global_id,
                :wallet_address,
                TRUE,
                TRUE,
                TRUE
            )
            """
        ),
        {
            "global_id": ton_global_id,
            "wallet_address": "0:" + ("44" * 32),
        },
    )
    await db_session.commit()

    pending = await complete_task(
        db_session,
        global_id=ton_global_id,
        task_code="cycle1644_ad",
        proof={},
        idempotency_key="cycle1644-ad-credit",
    )
    assert pending["ok"] is True
    assert pending["bonus_efhc"] == Decimal("0")

    credited = await confirm_ad_view_and_credit(
        db_session,
        global_id=ton_global_id,
        task_code="cycle1644_ad",
        provider="test",
        provider_ref="cycle1644",
        bonus_efhc=Decimal("1.25000000"),
        idempotency_key="cycle1644-ad-credit",
    )
    assert credited["ok"] is True
    assert credited["bonus_efhc"] == Decimal("1.25000000")

    owner_row = (
        await db_session.execute(
            text(
                """
                SELECT global_id
                  FROM efhc_core.task_bonus_log
                 WHERE idempotency_key = :idk
                """
            ),
            {"idk": "cycle1644-ad-credit"},
        )
    ).one()
    assert int(owner_row.global_id) == ton_global_id

    tasks = await list_available_tasks(
        db_session,
        global_id=ton_global_id,
    )
    assert any(
        item.task_code == "cycle1644_ad"
        for item in tasks.items
    )
    rewards = await list_task_bonus_log(
        db_session,
        global_id=ton_global_id,
    )
    assert len(rewards.items) == 1

    wallets = await list_wallets(
        db_session,
        global_id=f"{ton_global_id:010d}",
    )
    assert len(wallets) == 1
    assert await has_active_wallet(
        db_session,
        global_id=f"{ton_global_id:010d}",
    )

    meta = await rebuild_rank_snapshot(db_session)
    assert meta.total_users >= 2
    me, top, _ = await get_user_rank_and_top(
        db_session,
        global_id=ton_global_id,
        top_limit=10,
    )
    assert me is not None
    assert me.global_id == ton_global_id
    assert any(
        item.global_id == telegram_global_id
        for item in top
    )

    page, _, _ = await get_leaderboard_page(
        db_session,
        after_cursor=None,
        page_size=10,
        global_read=True,
    )
    assert any(item.global_id == ton_global_id for item in page)


@pytest.mark.asyncio
async def test_canonical_global_owner_разрешает_задачи_и_кошелёк(
    db_session: AsyncSession,
) -> None:
    global_id = await _seed_owner(
        db_session,
        tg_id=916440002,
        total_kwh="1.00000000",
    )
    await db_session.execute(
        text(
            """
            INSERT INTO efhc_core.wallet_bindings (
                global_id,
                wallet_address,
                is_primary,
                is_active,
                proof_verified
            ) VALUES (
                :global_id,
                :wallet_address,
                TRUE,
                TRUE,
                TRUE
            )
            """
        ),
        {
            "global_id": global_id,
            "wallet_address": "0:" + ("45" * 32),
        },
    )
    await db_session.commit()

    by_global = await list_wallets(
        db_session,
        global_id=f"{global_id:010d}",
    )
    assert len(by_global) == 1
    assert await has_active_wallet(
        db_session,
        global_id=f"{global_id:010d}",
    )
