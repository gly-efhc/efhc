from __future__ import annotations

from decimal import Decimal

import pytest
from app.services import referral_service
from app.services.referral_service import (
    ReferralOnboardingRejected,
    onboard_user_at_first_creation,
)
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def _insert_user(db_session, tg_id: int, balance: str = "0") -> int:
    global_id = int(
        (
            await db_session.execute(
                text(
                    """
                    INSERT INTO efhc_core.users (
                        username, is_active, main_balance,
                        bonus_balance, total_generated_kwh,
                        created_at, updated_at
                    )
                    VALUES (NULL, TRUE, :balance, 0, 0, now(), now())
                    RETURNING global_id
                    """
                ),
                {"balance": balance},
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


async def _insert_code(db_session, tg_id: int, code: str) -> None:
    global_id = await _global_id_for_tg(db_session, tg_id)
    await db_session.execute(
        text(
            """
            INSERT INTO efhc_core.referral_codes (
                code, inviter_global_id
            ) VALUES (:code, :global_id)
            """
        ),
        {"code": code, "global_id": global_id},
    )
    await db_session.commit()


async def _scalar(db_session, query: str, **params):
    return (await db_session.execute(text(query), params)).scalar_one()


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


async def test_referral_is_fixed_only_at_first_user_creation(
    db_session,
) -> None:
    inviter_a = 778001
    invitee_b = 778002
    zero_c = 778003

    await _insert_user(db_session, inviter_a)
    await _insert_code(db_session, inviter_a, "INVITEA1")

    b = await onboard_user_at_first_creation(
        db_session,
        tg_id=invitee_b,
        username="invitee_b",
        start_param="ref_INVITEA1",
    )
    assert b.created is True
    assert b.referral_attached is True
    assert b.inviter_global_id == await _global_id_for_tg(
        db_session, inviter_a
    )

    c = await onboard_user_at_first_creation(
        db_session,
        tg_id=zero_c,
        username="zero_c",
        start_param=None,
    )
    assert c.created is True
    assert c.referral_attached is False
    assert c.reason == "created_zero_user"

    await _insert_code(db_session, invitee_b, "INVITEB1")
    locked = await onboard_user_at_first_creation(
        db_session,
        tg_id=zero_c,
        username="zero_c",
        start_param="ref_INVITEB1",
    )
    assert locked.created is False
    assert locked.reason == "existing_user_locked"

    links = await _scalar(
        db_session,
        "SELECT COUNT(*) FROM efhc_core.referral_links",
    )
    c_links = await _scalar(
        db_session,
        "SELECT COUNT(*) FROM efhc_core.referral_links "
        "WHERE invitee_global_id = :global_id",
        global_id=await _global_id_for_tg(db_session, zero_c),
    )
    assert int(links) == 1
    assert int(c_links) == 0


async def test_direct_and_transitive_cycles_are_constructively_impossible(
    db_session,
) -> None:
    a, b, c = 778011, 778012, 778013
    await _insert_user(db_session, a)
    await _insert_code(db_session, a, "CYCLEA11")

    await onboard_user_at_first_creation(
        db_session,
        tg_id=b,
        start_param="ref_CYCLEA11",
    )
    await _insert_code(db_session, b, "CYCLEB12")
    await onboard_user_at_first_creation(
        db_session,
        tg_id=c,
        start_param="ref_CYCLEB12",
    )
    await _insert_code(db_session, c, "CYCLEC13")

    direct = await onboard_user_at_first_creation(
        db_session,
        tg_id=a,
        start_param="ref_CYCLEB12",
    )
    transitive = await onboard_user_at_first_creation(
        db_session,
        tg_id=a,
        start_param="ref_CYCLEC13",
    )
    assert direct.reason == "existing_user_locked"
    assert transitive.reason == "existing_user_locked"

    edges = (
        await db_session.execute(
            text(
                "SELECT inviter_global_id, invitee_global_id "
                "FROM efhc_core.referral_links ORDER BY id"
            )
        )
    ).all()
    assert [(int(x[0]), int(x[1])) for x in edges] == [
        (
            await _global_id_for_tg(db_session, a),
            await _global_id_for_tg(db_session, b),
        ),
        (
            await _global_id_for_tg(db_session, b),
            await _global_id_for_tg(db_session, c),
        ),
    ]


async def test_invalid_new_referral_does_not_create_user(
    db_session,
) -> None:
    tg_id = 778021
    with pytest.raises(ReferralOnboardingRejected) as exc:
        await onboard_user_at_first_creation(
            db_session,
            tg_id=tg_id,
            start_param="ref_DOES_NOT_EXIST",
        )
    assert exc.value.reason == "code_not_found"
    users = await _scalar(
        db_session,
        "SELECT COUNT(*) FROM efhc_core.user_identities "
        "WHERE provider='telegram' AND provider_tenant='default' "
        "AND provider_subject=:subject",
        subject=str(tg_id),
    )
    assert int(users) == 0


async def test_referral_insert_failure_rolls_back_new_user(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inviter, invitee = 778031, 778032
    await _insert_user(db_session, inviter)
    await _insert_code(db_session, inviter, "ROLLBACK31")

    async def _fail(*args, **kwargs) -> None:
        _ = args, kwargs
        raise RuntimeError("forced referral insert failure")

    monkeypatch.setattr(
        referral_service,
        "_create_bot_user_identity",
        _fail,
    )
    with pytest.raises(RuntimeError, match="forced referral insert failure"):
        await onboard_user_at_first_creation(
            db_session,
            tg_id=invitee,
            start_param="ref_ROLLBACK31",
        )

    users = await _scalar(
        db_session,
        "SELECT COUNT(*) FROM efhc_core.user_identities "
        "WHERE provider='telegram' AND provider_tenant='default' "
        "AND provider_subject=:subject",
        subject=str(invitee),
    )
    links = await _scalar(
        db_session,
        "SELECT COUNT(*) FROM efhc_core.referral_links",
    )
    assert int(users) == 0
    assert int(links) == 0


async def test_zero_user_first_panel_creates_no_referral_bonus(
    db_session,
) -> None:
    from app.services.panels_service import activate_panel

    zero_tg = 778041
    created = await onboard_user_at_first_creation(
        db_session,
        tg_id=zero_tg,
        start_param=None,
    )
    assert created.reason == "created_zero_user"
    await db_session.execute(
        text(
            "UPDATE efhc_core.users SET main_balance = 100 "
            "WHERE global_id = :global_id"
        ),
        {"global_id": await _global_id_for_tg(db_session, zero_tg)},
    )
    await db_session.commit()

    result = await activate_panel(
        db_session,
        global_id=await _global_id_for_tg(db_session, zero_tg),
        qty=1,
        idempotency_key="panel:zero-user:778041",
    )
    assert result.ok is True

    links = await _scalar(
        db_session,
        "SELECT COUNT(*) FROM efhc_core.referral_links "
        "WHERE invitee_global_id = :global_id",
        global_id=await _global_id_for_tg(db_session, zero_tg),
    )
    rewards = await _scalar(
        db_session,
        "SELECT COUNT(*) FROM efhc_core.efhc_transfers_log "
        "WHERE reason = 'referral_active_unit'",
    )
    bonus = await _scalar(
        db_session,
        "SELECT bonus_balance FROM efhc_core.users "
        "WHERE global_id = :global_id",
        global_id=await _global_id_for_tg(db_session, zero_tg),
    )
    assert int(links) == 0
    assert int(rewards) == 0
    assert Decimal(str(bonus)) == Decimal("0.00000000")
