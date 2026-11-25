from __future__ import annotations

from decimal import Decimal

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
text = sqlalchemy.text

pytestmark = pytest.mark.asyncio


async def _ensure_user(
    db_session,
    *,
    tg_id: int,
    main_balance: str,
) -> int:
    global_id = int(
        (
            await db_session.execute(
                text(
                    """
                    INSERT INTO efhc_core.users (
                        username, is_vip, is_active, main_balance,
                        bonus_balance, total_generated_kwh,
                        created_at, updated_at
                    )
                    VALUES (
                        NULL, FALSE, TRUE, :main, 0, 0, now(), now()
                    )
                    RETURNING global_id
                    """
                ),
                {"main": str(main_balance)},
            )
        ).scalar_one()
    )
    await db_session.execute(
        text(
            """
            INSERT INTO efhc_core.user_identities (
                global_id, provider, provider_tenant, provider_subject,
                status, is_primary, is_verified, verified_at
            ) VALUES (
                :global_id, 'telegram', 'default', :subject,
                'active', TRUE, TRUE, now()
            )
            """
        ),
        {"global_id": global_id, "subject": str(int(tg_id))},
    )
    await db_session.commit()
    return global_id



async def _prepare_referral(
    db_session,
    *,
    inviter_tg: int,
    buyer_tg: int,
) -> None:
    inviter_global = await _ensure_user(
        db_session,
        tg_id=inviter_tg,
        main_balance="0.00000000",
    )
    buyer_global = await _ensure_user(
        db_session,
        tg_id=buyer_tg,
        main_balance="100.00000000",
    )
    await db_session.execute(
        text(
            """
            INSERT INTO efhc_core.referral_links (
                inviter_global_id,
                invitee_global_id,
                created_at,
                activated_at
            )
            VALUES (
                :inviter_global, :buyer_global, now(), NULL
            )
            """
        ),
        {
            "inviter_global": inviter_global,
            "buyer_global": buyer_global,
        },
    )
    await db_session.commit()


async def _scalar(db_session, query: str, **params):
    return (
        await db_session.execute(text(query), params)
    ).scalar_one()


async def _global_id_for_tg(db_session, tg_id: int) -> int:
    return int(
        (
            await db_session.execute(
                text(
                    "SELECT global_id FROM efhc_core.user_identities "
                    "WHERE provider='telegram' "
                    "AND provider_tenant='default' "
                    "AND status='active' "
                    "AND provider_subject=:subject"
                ),
                {"subject": str(int(tg_id))},
            )
        ).scalar_one()
    )


async def test_first_panel_activates_referral_and_rewards_once(
    db_session,
) -> None:
    from app.services.panels_service import activate_panel

    inviter_tg = 771001
    buyer_tg = 771002
    idempotency_key = "panel:first-referral:771002"
    await _prepare_referral(
        db_session,
        inviter_tg=inviter_tg,
        buyer_tg=buyer_tg,
    )

    result = await activate_panel(
        db_session,
        global_id=await _global_id_for_tg(db_session, buyer_tg),
        qty=1,
        idempotency_key=idempotency_key,
    )
    assert result.ok is True

    activated = await _scalar(
        db_session,
        "SELECT activated_at IS NOT NULL "
        "FROM efhc_core.referral_links "
        "WHERE invitee_global_id = :buyer_global",
        buyer_global=await _global_id_for_tg(db_session, buyer_tg),
    )
    inviter_bonus = await _scalar(
        db_session,
        "SELECT bonus_balance FROM efhc_core.users "
        "WHERE global_id = :inviter_global",
        inviter_global=await _global_id_for_tg(db_session, inviter_tg),
    )
    panel_count = await _scalar(
        db_session,
        "SELECT COUNT(*) FROM efhc_core.panels "
        "WHERE global_id = :buyer_global",
        buyer_global=await _global_id_for_tg(db_session, buyer_tg),
    )
    reward_count = await _scalar(
        db_session,
        "SELECT COUNT(*) FROM efhc_core.efhc_transfers_log "
        "WHERE idempotency_key = :idk",
        idk=f"REF_ACT_UNIT:G{await _global_id_for_tg(db_session, inviter_tg):010d}:N00001",
    )

    assert activated is True
    assert Decimal(str(inviter_bonus)) == Decimal("0.10000000")
    assert int(panel_count) == 1
    assert int(reward_count) == 1

    replay = await activate_panel(
        db_session,
        global_id=await _global_id_for_tg(db_session, buyer_tg),
        qty=1,
        idempotency_key=idempotency_key,
    )
    assert replay.ok is True

    replay_bonus = await _scalar(
        db_session,
        "SELECT bonus_balance FROM efhc_core.users "
        "WHERE global_id = :inviter_global",
        inviter_global=await _global_id_for_tg(db_session, inviter_tg),
    )
    replay_panels = await _scalar(
        db_session,
        "SELECT COUNT(*) FROM efhc_core.panels "
        "WHERE global_id = :buyer_global",
        buyer_global=await _global_id_for_tg(db_session, buyer_tg),
    )
    replay_rewards = await _scalar(
        db_session,
        "SELECT COUNT(*) FROM efhc_core.efhc_transfers_log "
        "WHERE idempotency_key = :idk",
        idk=f"REF_ACT_UNIT:G{await _global_id_for_tg(db_session, inviter_tg):010d}:N00001",
    )

    assert Decimal(str(replay_bonus)) == Decimal("0.10000000")
    assert int(replay_panels) == 1
    assert int(replay_rewards) == 1


async def test_referral_failure_rolls_back_panel_and_debit(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import panels_service

    inviter_tg = 771011
    buyer_tg = 771012
    idempotency_key = "panel:referral-rollback:771012"
    await _prepare_referral(
        db_session,
        inviter_tg=inviter_tg,
        buyer_tg=buyer_tg,
    )

    async def _fail_referral(*args, **kwargs) -> None:
        _ = args, kwargs
        raise RuntimeError("forced referral failure")

    monkeypatch.setattr(
        panels_service.referral_service,
        "_maybe_reward_active_unit_bonus",
        _fail_referral,
    )

    with pytest.raises(panels_service.PanelPurchaseError):
        await panels_service.activate_panel(
            db_session,
            global_id=await _global_id_for_tg(db_session, buyer_tg),
            qty=1,
            idempotency_key=idempotency_key,
        )

    buyer_main = await _scalar(
        db_session,
        "SELECT main_balance FROM efhc_core.users "
        "WHERE global_id = :buyer_global",
        buyer_global=await _global_id_for_tg(db_session, buyer_tg),
    )
    panel_count = await _scalar(
        db_session,
        "SELECT COUNT(*) FROM efhc_core.panels "
        "WHERE global_id = :buyer_global",
        buyer_global=await _global_id_for_tg(db_session, buyer_tg),
    )
    activated = await _scalar(
        db_session,
        "SELECT activated_at IS NOT NULL "
        "FROM efhc_core.referral_links "
        "WHERE invitee_global_id = :buyer_global",
        buyer_global=await _global_id_for_tg(db_session, buyer_tg),
    )
    debit_count = await _scalar(
        db_session,
        "SELECT COUNT(*) FROM efhc_core.efhc_transfers_log "
        "WHERE idempotency_key IN (:bonus_idk, :main_idk)",
        bonus_idk=f"{idempotency_key}:bonus",
        main_idk=f"{idempotency_key}:main",
    )

    assert Decimal(str(buyer_main)) == Decimal("100.00000000")
    assert int(panel_count) == 0
    assert activated is False
    assert int(debit_count) == 0
