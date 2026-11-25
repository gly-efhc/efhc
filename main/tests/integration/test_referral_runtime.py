"""Real PostgreSQL proof for referral attribution and monetary truth."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.crud.referrals_crud import (
    activate_referral,
    admin_top_inviters,
    count_total_and_active,
    list_active_refs_cursor,
    list_inactive_refs_cursor,
)
from app.services import referral_service
from app.services.admin.admin_users_service import _get_referrals_brief
from app.services.panels_service import (
    PanelPurchaseError,
    activate_panel,
)
from app.services.referral_service import (
    SQL_LIST_REFERRALS_GLOBAL,
    ReferralOnboardingRejected,
    _count_active_referrals,
    _maybe_reward_active_unit_bonus,
    _sync_inviter_level_rewards,
    admin_summary,
    get_counters,
    get_or_create_referral_code,
    list_active_referrals,
    onboard_user_at_first_creation,
    svc_list_referrals_active,
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

TG_BASE = 8_841_000_000_000
INVITER_TG = TG_BASE
INVITEE_TG = TG_BASE + 1

PANEL_QUERY_INDEXES = {
    "ix_panels_global_id",
    "ix_panels_global_active",
    "ix_panels_global_expire",
    "ix_panels_global_activated",
}


def _walk_plan_nodes(
    value: object,
) -> Iterator[dict[str, object]]:
    """Yield every PostgreSQL plan node from FORMAT JSON output."""
    if isinstance(value, dict):
        if "Node Type" in value:
            yield value
        for nested in value.values():
            yield from _walk_plan_nodes(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_plan_nodes(nested)


def _plan_index_names(plan: object) -> set[str]:
    return {
        str(node["Index Name"])
        for node in _walk_plan_nodes(plan)
        if node.get("Index Name")
    }


async def _create_user(
    db: AsyncSession,
    *,
    tg_id: int,
    username: str | None = None,
    main_balance: str = "0",
    bonus_balance: str = "0",
) -> int:
    global_id = (
        await db.execute(
            text(
                """
                INSERT INTO efhc_core.users (
                    username,
                    main_balance,
                    bonus_balance,
                    is_active
                )
                VALUES (
                    :username,
                    :main_balance,
                    :bonus_balance,
                    TRUE
                )
                RETURNING global_id
                """
            ),
            {
                "username": username,
                "main_balance": main_balance,
                "bonus_balance": bonus_balance,
            },
        )
    ).scalar_one()
    await db.execute(
        text(
            """
            INSERT INTO efhc_core.user_identities (
                global_id,
                provider,
                provider_tenant,
                provider_subject,
                status,
                is_primary,
                is_verified,
                verified_at
            )
            VALUES (
                :global_id,
                'telegram',
                'default',
                :provider_subject,
                'active',
                TRUE,
                TRUE,
                NOW()
            )
            """
        ),
        {
            "global_id": int(global_id),
            "provider_subject": str(int(tg_id)),
        },
    )
    await db.commit()
    return int(global_id)


async def _global_id_for_tg(db_session: AsyncSession, tg_id: int) -> int:
    return int(
        (
            await db_session.execute(
                text(
                    "SELECT global_id "
                    "FROM efhc_core.user_identities "
                    "WHERE provider = 'telegram' "
                    "AND provider_tenant = 'default' "
                    "AND provider_subject = :provider_subject "
                    "AND status = 'active'"
                ),
                {"provider_subject": str(int(tg_id))},
            )
        ).scalar_one()
    )


async def _create_referral_link(
    db: AsyncSession,
    *,
    invitee_tg_id: int,
    inviter_tg_id: int = INVITER_TG,
    activated: bool = False,
    created_at: datetime | None = None,
) -> None:
    created = created_at or datetime.now(UTC)
    await db.execute(
        text(
            """
            INSERT INTO efhc_core.referral_links (
                inviter_global_id,
                invitee_global_id,
                created_at,
                activated_at
            )
            VALUES (
                :inviter_global_id,
                :invitee_global_id,
                CAST(:created_at AS TIMESTAMPTZ),
                CASE
                    WHEN CAST(:activated AS BOOLEAN)
                    THEN CAST(:created_at AS TIMESTAMPTZ)
                    ELSE NULL
                END
            )
            """
        ),
        {
            "inviter_global_id": await _global_id_for_tg(
                db, inviter_tg_id
            ),
            "invitee_global_id": await _global_id_for_tg(
                db, invitee_tg_id
            ),
            "created_at": created,
            "activated": bool(activated),
        },
    )
    await db.commit()


async def _add_panel(
    db: AsyncSession,
    *,
    tg_id: int,
    public_id: str,
    archived: bool = False,
) -> None:
    now = datetime.now(UTC)
    await db.execute(
        text(
            """
            INSERT INTO efhc_core.panels (
                global_id,
                public_id,
                is_active,
                is_archived,
                activated_at,
                expires_at,
                archived_at,
                last_generated_at,
                base_gen_per_sec,
                generated_kwh
            )
            VALUES (
                :global_id,
                :public_id,
                :is_active,
                :is_archived,
                :activated_at,
                :expires_at,
                :archived_at,
                :activated_at,
                0,
                0
            )
            """
        ),
        {
            "global_id": await _global_id_for_tg(db, tg_id),
            "public_id": public_id,
            "is_active": not archived,
            "is_archived": archived,
            "activated_at": now,
            "expires_at": now + timedelta(days=180),
            "archived_at": now if archived else None,
        },
    )
    await db.commit()


async def _add_active_referrals(
    db: AsyncSession,
    *,
    start_index: int,
    end_index: int,
    inviter_tg_id: int = INVITER_TG,
    base_tg_id: int = TG_BASE + 100_000,
) -> None:
    assert end_index >= start_index
    await db.execute(
        text(
            """
            INSERT INTO efhc_core.users (
                username,
                main_balance,
                bonus_balance,
                is_active
            )
            SELECT
                'ref_' || (CAST(:base_tg AS BIGINT) + gs)::TEXT,
                0,
                0,
                TRUE
            FROM generate_series(
                CAST(:start_index AS BIGINT),
                CAST(:end_index AS BIGINT)
            ) AS gs
            """
        ),
        {
            "base_tg": int(base_tg_id),
            "start_index": int(start_index),
            "end_index": int(end_index),
        },
    )
    await db.execute(
        text(
            """
            INSERT INTO efhc_core.user_identities (
                global_id,
                provider,
                provider_tenant,
                provider_subject,
                status,
                is_primary,
                is_verified,
                verified_at
            )
            SELECT
                u.global_id,
                'telegram',
                'default',
                (CAST(:base_tg AS BIGINT) + gs)::TEXT,
                'active',
                TRUE,
                TRUE,
                NOW()
            FROM generate_series(
                CAST(:start_index AS BIGINT),
                CAST(:end_index AS BIGINT)
            ) AS gs
            JOIN efhc_core.users AS u
              ON u.username =
                 'ref_' || (CAST(:base_tg AS BIGINT) + gs)::TEXT
            """
        ),
        {
            "base_tg": int(base_tg_id),
            "start_index": int(start_index),
            "end_index": int(end_index),
        },
    )
    await db.execute(
        text(
            """
            INSERT INTO efhc_core.referral_links (
                inviter_global_id,
                invitee_global_id,
                created_at,
                activated_at
            )
            SELECT
                inviter_identity.global_id,
                invitee_identity.global_id,
                NOW() + (gs * INTERVAL '1 microsecond'),
                NOW()
            FROM generate_series(
                CAST(:start_index AS BIGINT),
                CAST(:end_index AS BIGINT)
            ) AS gs
            JOIN efhc_core.user_identities AS invitee_identity
              ON invitee_identity.provider = 'telegram'
             AND invitee_identity.provider_tenant = 'default'
             AND invitee_identity.provider_subject =
                 (CAST(:base_tg AS BIGINT) + gs)::TEXT
            CROSS JOIN efhc_core.user_identities AS inviter_identity
            WHERE inviter_identity.provider = 'telegram'
              AND inviter_identity.provider_tenant = 'default'
              AND inviter_identity.provider_subject = :inviter_subject
            """
        ),
        {
            "inviter_subject": str(int(inviter_tg_id)),
            "base_tg": int(base_tg_id),
            "start_index": int(start_index),
            "end_index": int(end_index),
        },
    )
    await db.execute(
        text(
            """
            INSERT INTO efhc_core.panels (
                global_id,
                public_id,
                is_active,
                is_archived,
                activated_at,
                expires_at,
                last_generated_at,
                base_gen_per_sec,
                generated_kwh
            )
            SELECT
                identity.global_id,
                'IT' || LPAD(gs::TEXT, 12, '0'),
                TRUE,
                FALSE,
                NOW(),
                NOW() + INTERVAL '180 days',
                NOW(),
                0,
                0
            FROM generate_series(
                CAST(:start_index AS BIGINT),
                CAST(:end_index AS BIGINT)
            ) AS gs
            JOIN efhc_core.user_identities AS identity
              ON identity.provider = 'telegram'
             AND identity.provider_tenant = 'default'
             AND identity.provider_subject =
                 (CAST(:base_tg AS BIGINT) + gs)::TEXT
            """
        ),
        {
            "base_tg": int(base_tg_id),
            "start_index": int(start_index),
            "end_index": int(end_index),
        },
    )
    await db.commit()


async def _scalar_decimal(
    db: AsyncSession,
    sql: str,
    params: dict[str, object],
) -> Decimal:
    value = (await db.execute(text(sql), params)).scalar_one()
    return Decimal(str(value))


async def _onboard_referral_pair(
    db: AsyncSession,
    *,
    invitee_tg_id: int,
    inviter_tg_id: int = INVITER_TG,
    invitee_main_balance: str = "100",
) -> None:
    """Create the real first-creation referral path used by production."""
    inviter = await onboard_user_at_first_creation(
        db,
        tg_id=int(inviter_tg_id),
        username=f"inviter_{inviter_tg_id}",
    )
    assert inviter.created is True
    code = await get_or_create_referral_code(
        db,
        inviter_global_id=await _global_id_for_tg(db, inviter_tg_id),
    )
    invitee = await onboard_user_at_first_creation(
        db,
        tg_id=int(invitee_tg_id),
        username=f"invitee_{invitee_tg_id}",
        start_param=f"ref_{code}",
    )
    assert invitee.created is True
    assert invitee.referral_attached is True
    assert invitee.inviter_global_id == await _global_id_for_tg(
        db, inviter_tg_id
    )
    await db.execute(
        text(
            "UPDATE efhc_core.users SET main_balance = :balance "
            "WHERE global_id = :global_id"
        ),
        {
            "balance": invitee_main_balance,
            "global_id": await _global_id_for_tg(db, invitee_tg_id),
        },
    )
    await db.commit()


async def test_registration_by_referral_link_creates_no_bonus(
    db_session: AsyncSession,
) -> None:
    await _create_user(db_session, tg_id=INVITER_TG, username="inviter")
    code = await get_or_create_referral_code(
        db_session,
        inviter_global_id=await _global_id_for_tg(
            db_session, INVITER_TG
        ),
    )
    result = await onboard_user_at_first_creation(
        db_session,
        tg_id=INVITEE_TG,
        username="invitee",
        start_param=f"ref_{code}",
    )
    assert result.created is True
    assert result.referral_attached is True
    assert result.inviter_global_id == await _global_id_for_tg(
        db_session, INVITER_TG
    )
    row = (
        await db_session.execute(
            text(
                "SELECT activated_at FROM efhc_core.referral_links "
                "WHERE invitee_global_id = :global_id"
            ),
            {
                "global_id": await _global_id_for_tg(
                    db_session, INVITEE_TG
                )
            },
        )
    ).one()
    assert row.activated_at is None
    logs = (
        await db_session.execute(
            text(
                "SELECT COUNT(*) FROM efhc_core.efhc_transfers_log "
                "WHERE reason IN "
                "('referral_active_unit', 'referral_level_bonus')"
            )
        )
    ).scalar_one()
    assert int(logs) == 0


async def test_invalid_code_is_rejected_before_user_creation(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(ReferralOnboardingRejected) as exc:
        await onboard_user_at_first_creation(
            db_session,
            tg_id=INVITEE_TG,
            start_param="ref_DOES_NOT_EXIST",
        )
    assert exc.value.reason == "code_not_found"
    count = (
        await db_session.execute(
            text(
                "SELECT COUNT(*) FROM efhc_core.user_identities "
                "WHERE provider = 'telegram' "
                "AND provider_tenant = 'default' "
                "AND provider_subject = :provider_subject"
            ),
            {"provider_subject": str(INVITEE_TG)},
        )
    ).scalar_one()
    assert int(count) == 0


async def test_existing_zero_user_cannot_attach_later(
    db_session: AsyncSession,
) -> None:
    await onboard_user_at_first_creation(db_session, tg_id=INVITEE_TG)
    await _create_user(db_session, tg_id=INVITER_TG)
    code = await get_or_create_referral_code(
        db_session,
        inviter_global_id=await _global_id_for_tg(
            db_session, INVITER_TG
        ),
    )
    result = await onboard_user_at_first_creation(
        db_session,
        tg_id=INVITEE_TG,
        start_param=f"ref_{code}",
    )
    assert result.created is False
    assert result.reason == "existing_user_locked"
    count = (
        await db_session.execute(
            text(
                "SELECT COUNT(*) FROM efhc_core.referral_links "
                "WHERE invitee_global_id = :global_id"
            ),
            {
                "global_id": await _global_id_for_tg(
                    db_session, INVITEE_TG
                )
            },
        )
    ).scalar_one()
    assert int(count) == 0


async def test_concurrent_first_creation_creates_one_user(
    db_session: AsyncSession,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _ = db_session

    async def attempt() -> object:
        async with integration_session_factory() as session:
            return await onboard_user_at_first_creation(
                session,
                tg_id=INVITEE_TG,
            )

    results = await asyncio.gather(attempt(), attempt())
    reasons = sorted(result.reason for result in results)
    assert reasons == ["created_zero_user", "existing_user_locked"]


async def test_referral_insert_failure_rolls_back_new_user(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _create_user(db_session, tg_id=INVITER_TG)
    code = await get_or_create_referral_code(
        db_session,
        inviter_global_id=await _global_id_for_tg(
            db_session, INVITER_TG
        ),
    )

    async def fail_insert(*args: object, **kwargs: object) -> None:
        _ = args, kwargs
        raise RuntimeError("forced referral relation failure")

    monkeypatch.setattr(
        referral_service,
        "_create_bot_user_identity",
        fail_insert,
    )
    with pytest.raises(RuntimeError):
        await onboard_user_at_first_creation(
            db_session,
            tg_id=INVITEE_TG,
            start_param=f"ref_{code}",
        )
    user_count = (
        await db_session.execute(
            text(
                "SELECT COUNT(*) FROM efhc_core.user_identities "
                "WHERE provider = 'telegram' "
                "AND provider_tenant = 'default' "
                "AND provider_subject = :provider_subject"
            ),
            {"provider_subject": str(INVITEE_TG)},
        )
    ).scalar_one()
    assert int(user_count) == 0


async def test_zero_user_first_panel_creates_no_referral_bonus(
    db_session: AsyncSession,
) -> None:
    result = await onboard_user_at_first_creation(
        db_session,
        tg_id=INVITEE_TG,
    )
    assert result.created is True
    assert result.referral_attached is False
    assert result.reason == "created_zero_user"
    await db_session.execute(
        text(
            "UPDATE efhc_core.users SET main_balance = 100 "
            "WHERE global_id = :global_id"
        ),
        {
                "global_id": await _global_id_for_tg(
                    db_session, INVITEE_TG
                )
            },
    )
    await db_session.commit()
    result = await activate_panel(
        db_session,
        global_id=await _global_id_for_tg(db_session, INVITEE_TG),
        qty=1,
        idempotency_key="IT:REF:ZERO:USER",
    )
    assert result.ok is True
    referral_logs = (
        await db_session.execute(
            text(
                "SELECT COUNT(*) "
                "FROM efhc_core.efhc_transfers_log "
                "WHERE reason IN "
                "('referral_active_unit', 'referral_level_bonus')"
            )
        )
    ).scalar_one()
    assert int(referral_logs) == 0


async def test_database_rejects_self_referral(
    db_session: AsyncSession,
) -> None:
    await _create_user(db_session, tg_id=INVITER_TG)
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO efhc_core.referral_links "
                "(inviter_global_id, invitee_global_id) "
                "VALUES (:global_id, :global_id)"
            ),
            {
                "global_id": await _global_id_for_tg(
                    db_session, INVITER_TG
                )
            },
        )
        await db_session.commit()
    await db_session.rollback()


async def test_first_panel_credits_exactly_point_one_and_replays_once(
    db_session: AsyncSession,
) -> None:
    """Real onboarding -> first panel -> bonus -> idempotent replay."""
    await _onboard_referral_pair(
        db_session,
        invitee_tg_id=INVITEE_TG,
    )
    before_activation = (
        await db_session.execute(
            text(
                "SELECT activated_at FROM efhc_core.referral_links "
                "WHERE invitee_global_id = :global_id"
            ),
            {
                "global_id": await _global_id_for_tg(
                    db_session, INVITEE_TG
                )
            },
        )
    ).scalar_one()
    assert before_activation is None

    key = "IT:REF:FIRST_PANEL"
    first = await activate_panel(
        db_session,
        global_id=await _global_id_for_tg(db_session, INVITEE_TG),
        qty=1,
        idempotency_key=key,
    )
    second = await activate_panel(
        db_session,
        global_id=await _global_id_for_tg(db_session, INVITEE_TG),
        qty=1,
        idempotency_key=key,
    )
    assert first.created_panel_ids == second.created_panel_ids

    inviter_bonus = await _scalar_decimal(
        db_session,
        "SELECT bonus_balance FROM efhc_core.users "
        "WHERE global_id = :global_id",
        {"global_id": await _global_id_for_tg(db_session, INVITER_TG)},
    )
    invitee_balance = await _scalar_decimal(
        db_session,
        "SELECT main_balance FROM efhc_core.users "
        "WHERE global_id = :global_id",
        {
                "global_id": await _global_id_for_tg(
                    db_session, INVITEE_TG
                )
            },
    )
    activated_at = (
        await db_session.execute(
            text(
                "SELECT activated_at FROM efhc_core.referral_links "
                "WHERE invitee_global_id = :global_id"
            ),
            {
                "global_id": await _global_id_for_tg(
                    db_session, INVITEE_TG
                )
            },
        )
    ).scalar_one()
    unit_count = (
        await db_session.execute(
            text(
                "SELECT COUNT(*) FROM efhc_core.efhc_transfers_log "
                "WHERE idempotency_key = :key"
            ),
            {
                "key": (
                    "REF_ACT_UNIT:G"
                    f"{await _global_id_for_tg(db_session, INVITER_TG):010d}"
                    ":N00001"
                )
            },
        )
    ).scalar_one()
    panel_count = (
        await db_session.execute(
            text(
                "SELECT COUNT(*) FROM efhc_core.panels "
                "WHERE global_id = :global_id"
            ),
            {
                "global_id": await _global_id_for_tg(
                    db_session, INVITEE_TG
                )
            },
        )
    ).scalar_one()
    assert inviter_bonus == Decimal("0.10000000")
    assert invitee_balance == Decimal("0.00000000")
    assert activated_at is not None
    assert int(unit_count) == 1
    assert int(panel_count) == 1


async def test_failure_after_unit_before_level_rolls_back_everything(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _onboard_referral_pair(
        db_session,
        invitee_tg_id=INVITEE_TG,
    )

    async def fail_level(*args: object, **kwargs: object) -> None:
        _ = args, kwargs
        raise RuntimeError("forced failure after unit bonus")

    monkeypatch.setattr(
        referral_service,
        "_sync_inviter_level_rewards",
        fail_level,
    )
    with pytest.raises(PanelPurchaseError):
        await activate_panel(
            db_session,
            global_id=await _global_id_for_tg(db_session, INVITEE_TG),
            qty=1,
            idempotency_key="IT:REF:ROLLBACK",
        )
    panel_count = (
        await db_session.execute(
            text(
                "SELECT COUNT(*) FROM efhc_core.panels "
                "WHERE global_id = :global_id"
            ),
            {
                "global_id": await _global_id_for_tg(
                    db_session, INVITEE_TG
                )
            },
        )
    ).scalar_one()
    logs = (
        await db_session.execute(
            text(
                "SELECT COUNT(*) FROM efhc_core.efhc_transfers_log "
                "WHERE tg_id IN (:inviter, :invitee)"
            ),
            {"inviter": INVITER_TG, "invitee": INVITEE_TG},
        )
    ).scalar_one()
    activated_at = (
        await db_session.execute(
            text(
                "SELECT activated_at FROM efhc_core.referral_links "
                "WHERE invitee_global_id = :global_id"
            ),
            {
                "global_id": await _global_id_for_tg(
                    db_session, INVITEE_TG
                )
            },
        )
    ).scalar_one()
    main_balance = await _scalar_decimal(
        db_session,
        "SELECT main_balance FROM efhc_core.users "
        "WHERE global_id = :global_id",
        {
                "global_id": await _global_id_for_tg(
                    db_session, INVITEE_TG
                )
            },
    )
    assert int(panel_count) == 0
    assert int(logs) == 0
    assert activated_at is None
    assert main_balance == Decimal("100.00000000")


async def test_parallel_first_panel_requests_create_two_panels_one_bonus(
    db_session: AsyncSession,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _onboard_referral_pair(
        db_session,
        invitee_tg_id=INVITEE_TG,
        invitee_main_balance="200",
    )

    invitee_global_id = await _global_id_for_tg(
        db_session, INVITEE_TG
    )

    async def purchase(key: str) -> None:
        async with integration_session_factory() as session:
            result = await activate_panel(
                session,
                global_id=invitee_global_id,
                qty=1,
                idempotency_key=key,
            )
            assert result.ok is True

    await asyncio.gather(
        purchase("IT:REF:PARALLEL:A"),
        purchase("IT:REF:PARALLEL:B"),
    )
    panel_count = (
        await db_session.execute(
            text(
                "SELECT COUNT(*) FROM efhc_core.panels "
                "WHERE global_id = :global_id"
            ),
            {
                "global_id": await _global_id_for_tg(
                    db_session, INVITEE_TG
                )
            },
        )
    ).scalar_one()
    unit_count = (
        await db_session.execute(
            text(
                "SELECT COUNT(*) FROM efhc_core.efhc_transfers_log "
                "WHERE reason = 'referral_active_unit' "
                "AND tg_id = :tg"
            ),
            {"tg": INVITER_TG},
        )
    ).scalar_one()
    assert int(panel_count) == 2
    assert int(unit_count) == 1


async def test_parallel_invitees_cross_one_level_without_conflict(
    db_session: AsyncSession,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _create_user(db_session, tg_id=INVITER_TG)
    await _add_active_referrals(
        db_session,
        start_index=1,
        end_index=9,
        base_tg_id=TG_BASE + 300_000,
    )
    buyers = (INVITEE_TG, INVITEE_TG + 1)
    for buyer in buyers:
        await _create_user(
            db_session,
            tg_id=buyer,
            main_balance="100",
        )
        await _create_referral_link(
            db_session,
            invitee_tg_id=buyer,
        )

    buyer_global_ids: dict[int, int] = {}
    for buyer in buyers:
        buyer_global_ids[buyer] = await _global_id_for_tg(
            db_session, buyer
        )

    async def purchase(buyer: int) -> None:
        async with integration_session_factory() as session:
            result = await activate_panel(
                session,
                global_id=buyer_global_ids[buyer],
                qty=1,
                idempotency_key=f"IT:REF:LEVEL:RACE:{buyer}",
            )
            assert result.ok is True

    await asyncio.gather(*(purchase(buyer) for buyer in buyers))
    inviter_global_id = await _global_id_for_tg(
        db_session, INVITER_TG
    )
    level_count = (
        await db_session.execute(
            text(
                "SELECT COUNT(*) FROM efhc_core.efhc_transfers_log "
                "WHERE global_id = :global_id "
                "AND reason = 'referral_level_bonus' "
                "AND idempotency_key = :key"
            ),
            {
                "global_id": inviter_global_id,
                "key": f"REF_LVL:G{inviter_global_id:010d}:L1",
            },
        )
    ).scalar_one()
    direct_count = (
        await db_session.execute(
            text(
                "SELECT COUNT(*) FROM efhc_core.efhc_transfers_log "
                "WHERE global_id = :global_id "
                "AND reason = 'referral_active_unit'"
            ),
            {"global_id": inviter_global_id},
        )
    ).scalar_one()
    bonus = await _scalar_decimal(
        db_session,
        (
            "SELECT bonus_balance FROM efhc_core.users "
            "WHERE global_id = :global_id"
        ),
        {"global_id": inviter_global_id},
    )
    assert int(level_count) == 1
    assert int(direct_count) == 2
    assert bonus == Decimal("1.20000000")


async def test_internal_user_pk_collision_does_not_activate_referral(
    db_session: AsyncSession,
) -> None:
    await _create_user(db_session, tg_id=INVITER_TG)
    await _create_user(db_session, tg_id=INVITEE_TG)
    await _create_referral_link(
        db_session,
        invitee_tg_id=INVITEE_TG,
    )
    internal_id = (
        await db_session.execute(
            text(
                "SELECT global_id FROM efhc_core.users "
                "WHERE global_id = :global_id"
            ),
            {
                "global_id": await _global_id_for_tg(
                    db_session, INVITEE_TG
                )
            },
        )
    ).scalar_one()
    await _create_user(
        db_session,
        tg_id=int(internal_id),
    )
    await _add_panel(
        db_session,
        tg_id=int(internal_id),
        public_id="ITPKCOLLISION",
    )
    assert await _count_active_referrals(
        db_session,
        inviter_global_id=await _global_id_for_tg(
            db_session, INVITER_TG
        ),
    ) == 0


async def test_archived_panel_keeps_referral_active(
    db_session: AsyncSession,
) -> None:
    await _create_user(db_session, tg_id=INVITER_TG)
    await _create_user(db_session, tg_id=INVITEE_TG)
    await _create_referral_link(
        db_session,
        invitee_tg_id=INVITEE_TG,
        activated=True,
    )
    await _add_panel(
        db_session,
        tg_id=INVITEE_TG,
        public_id="ITARCHIVED001",
        archived=True,
    )
    items, cursor = await svc_list_referrals_active(
        db_session,
        inviter_global_id=await _global_id_for_tg(
            db_session, INVITER_TG
        ),
        limit=10,
        cursor=None,
    )
    assert cursor is None
    assert [item.global_id for item in items] == [
        await _global_id_for_tg(db_session, INVITEE_TG)
    ]
    assert items[0].panels_count == 1
    activated_at = (
        await db_session.execute(
            text(
                "SELECT activated_at "
                "FROM efhc_core.referral_links "
                "WHERE invitee_global_id = :global_id"
            ),
            {
                "global_id": await _global_id_for_tg(
                    db_session, INVITEE_TG
                )
            },
        )
    ).scalar_one()
    assert activated_at is not None


async def test_active_status_is_permanent_and_ignores_panel_count(
    db_session: AsyncSession,
    next_referral_tg_id: Callable[[], int],
) -> None:
    """Activ is a permanent event flag, not current panel state.

    This test executes the real onboarding and first-panel purchase,
    physically deletes every invitee panel, then checks all three
    public/admin consumers of the status.
    """
    inviter_tg = next_referral_tg_id()
    invitee_tg = next_referral_tg_id()
    await _onboard_referral_pair(
        db_session,
        inviter_tg_id=inviter_tg,
        invitee_tg_id=invitee_tg,
    )
    inviter_global_id = await _global_id_for_tg(
        db_session, inviter_tg
    )
    invitee_global_id = await _global_id_for_tg(
        db_session, invitee_tg
    )
    purchase = await activate_panel(
        db_session,
        global_id=invitee_global_id,
        qty=1,
        idempotency_key=f"IT:ACTIV:PERMANENT:{invitee_tg}",
    )
    assert purchase.ok is True

    counters = await get_counters(
        db_session,
        parent_global_id=inviter_global_id,
    )
    active_page = await list_active_referrals(
        db_session,
        parent_global_id=inviter_global_id,
        limit=10,
    )
    summary = await admin_summary(db_session, limit=10)
    summary_row = next(
        row
        for row in summary["items"]
        if int(row["inviter_global_id"]) == inviter_global_id
    )
    assert counters.active == 1
    assert len(active_page.items) == 1
    assert active_page.items[0].is_active is True
    assert summary_row["active_count"] == 1
    admin_brief = await _get_referrals_brief(
        db_session,
        inviter_global_id,
    )
    assert admin_brief.active_invited == 1

    await db_session.execute(
        text(
            "DELETE FROM efhc_core.panels "
            "WHERE global_id = :global_id"
        ),
        {
                "global_id": invitee_global_id
            },
    )
    await db_session.commit()
    panels_left = (
        await db_session.execute(
            text(
                "SELECT COUNT(*) FROM efhc_core.panels "
                "WHERE global_id = :global_id"
            ),
            {
                "global_id": invitee_global_id
            },
        )
    ).scalar_one()
    assert int(panels_left) == 0

    counters_after = await get_counters(
        db_session,
        parent_global_id=inviter_global_id,
    )
    active_page_after = await list_active_referrals(
        db_session,
        parent_global_id=inviter_global_id,
        limit=10,
    )
    summary_after = await admin_summary(db_session, limit=10)
    summary_row_after = next(
        row
        for row in summary_after["items"]
        if int(row["inviter_global_id"]) == inviter_global_id
    )
    assert counters_after.active == 1
    assert len(active_page_after.items) == 1
    assert active_page_after.items[0].is_active is True
    assert active_page_after.items[0].panels_count == 0
    assert summary_row_after["active_count"] == 1
    admin_brief_after = await _get_referrals_brief(
        db_session,
        inviter_global_id,
    )
    assert admin_brief_after.active_invited == 1


async def test_activate_referral_owns_locked_transition_and_timestamp(
    db_session: AsyncSession,
) -> None:
    await _create_user(db_session, tg_id=INVITER_TG)
    await _create_user(db_session, tg_id=INVITEE_TG)
    await _create_referral_link(
        db_session,
        invitee_tg_id=INVITEE_TG,
    )
    first_ts = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
    later_ts = first_ts + timedelta(hours=1)

    first = await activate_referral(
        db_session,
        invitee_global_id=await _global_id_for_tg(
            db_session, INVITEE_TG
        ),
        activation_dt=first_ts,
    )
    second = await activate_referral(
        db_session,
        invitee_global_id=await _global_id_for_tg(
            db_session, INVITEE_TG
        ),
        activation_dt=later_ts,
    )
    await db_session.commit()

    assert first.activated_now is True
    assert first.link is not None
    assert first.link.activated_at == first_ts
    assert second.activated_now is False
    assert second.link is not None
    assert second.link.activated_at == first_ts


async def test_ten_end_to_end_referrals_produce_exact_lvl1_total(
    db_session: AsyncSession,
) -> None:
    """Ten real onboarding/panel flows yield 1 EFHCb + Lvl 1 = 2."""
    await onboard_user_at_first_creation(db_session, tg_id=INVITER_TG)
    code = await get_or_create_referral_code(
        db_session,
        inviter_global_id=await _global_id_for_tg(
            db_session, INVITER_TG
        ),
    )
    invitees = [TG_BASE + 10_000 + index for index in range(1, 11)]
    for invitee_tg in invitees:
        result = await onboard_user_at_first_creation(
            db_session,
            tg_id=invitee_tg,
            start_param=f"ref_{code}",
        )
        assert result.referral_attached is True
        await db_session.execute(
            text(
                "UPDATE efhc_core.users SET main_balance = 100 "
                "WHERE global_id = :global_id"
            ),
            {
                "global_id": await _global_id_for_tg(
                    db_session, invitee_tg
                )
            },
        )
        await db_session.commit()
        purchase = await activate_panel(
            db_session,
            global_id=await _global_id_for_tg(db_session, invitee_tg),
            qty=1,
            idempotency_key=f"IT:REF:LVL1:E2E:{invitee_tg}",
        )
        assert purchase.ok is True

    balance = await _scalar_decimal(
        db_session,
        "SELECT bonus_balance FROM efhc_core.users "
        "WHERE global_id = :global_id",
        {"global_id": await _global_id_for_tg(db_session, INVITER_TG)},
    )
    unit_logs = (
        await db_session.execute(
            text(
                "SELECT COUNT(*) FROM efhc_core.efhc_transfers_log "
                "WHERE global_id = :global_id "
                "AND reason = 'referral_active_unit'"
            ),
            {
                "global_id": await _global_id_for_tg(
                    db_session, INVITER_TG
                )
            },
        )
    ).scalar_one()
    level_logs = (
        await db_session.execute(
            text(
                "SELECT COUNT(*) FROM efhc_core.efhc_transfers_log "
                "WHERE global_id = :global_id "
                "AND reason = 'referral_level_bonus'"
            ),
            {
                "global_id": await _global_id_for_tg(
                    db_session, INVITER_TG
                )
            },
        )
    ).scalar_one()
    assert balance == Decimal("2.00000000")
    assert int(unit_logs) == 10
    assert int(level_logs) == 1


async def test_level_bonus_is_not_paid_before_threshold(
    db_session: AsyncSession,
) -> None:
    await _create_user(db_session, tg_id=INVITER_TG)
    await _add_active_referrals(
        db_session,
        start_index=1,
        end_index=9,
    )
    await _sync_inviter_level_rewards(
        db_session,
        inviter_global_id=await _global_id_for_tg(
            db_session, INVITER_TG
        ),
    )
    await db_session.commit()
    before = await _scalar_decimal(
        db_session,
        "SELECT bonus_balance "
        "FROM efhc_core.users WHERE global_id = :global_id",
        {"global_id": await _global_id_for_tg(db_session, INVITER_TG)},
    )
    assert before == Decimal("0.00000000")

    await _add_active_referrals(
        db_session,
        start_index=10,
        end_index=10,
    )
    await _sync_inviter_level_rewards(
        db_session,
        inviter_global_id=await _global_id_for_tg(
            db_session, INVITER_TG
        ),
    )
    await db_session.commit()
    after = await _scalar_decimal(
        db_session,
        "SELECT bonus_balance "
        "FROM efhc_core.users WHERE global_id = :global_id",
        {"global_id": await _global_id_for_tg(db_session, INVITER_TG)},
    )
    assert after == Decimal("1.00000000")


async def test_bank_deficit_mode_does_not_block_referral_bonus(
    db_session: AsyncSession,
) -> None:
    await _create_user(db_session, tg_id=INVITER_TG)
    await _create_user(db_session, tg_id=INVITEE_TG)
    await _create_referral_link(
        db_session,
        invitee_tg_id=INVITEE_TG,
        activated=True,
    )
    await _add_panel(
        db_session,
        tg_id=INVITEE_TG,
        public_id="ITDEFICIT001",
    )
    await _maybe_reward_active_unit_bonus(
        db_session,
        inviter_global_id=await _global_id_for_tg(
            db_session, INVITER_TG
        ),
        buyer_global_id=await _global_id_for_tg(
            db_session, INVITEE_TG
        ),
    )
    await db_session.commit()
    inviter_bonus = await _scalar_decimal(
        db_session,
        "SELECT bonus_balance "
        "FROM efhc_core.users WHERE global_id = :global_id",
        {"global_id": await _global_id_for_tg(db_session, INVITER_TG)},
    )
    bank_balance = await _scalar_decimal(
        db_session,
        "SELECT balance FROM efhc_core.bank_balance "
        "WHERE key = 'EFHC_MAIN'",
        {},
    )
    assert inviter_bonus == Decimal("0.10000000")
    assert bank_balance == Decimal("-0.10000000")


async def test_all_level_thresholds_are_idempotent(
    db_session: AsyncSession,
) -> None:
    await _create_user(db_session, tg_id=INVITER_TG)
    expected = [
        (10, Decimal("1.00000000"), 1),
        (100, Decimal("11.00000000"), 2),
        (1000, Decimal("111.00000000"), 3),
        (3000, Decimal("411.00000000"), 4),
        (10000, Decimal("1411.00000000"), 5),
    ]
    previous = 0
    for threshold, expected_bonus, expected_logs in expected:
        await _add_active_referrals(
            db_session,
            start_index=previous + 1,
            end_index=threshold,
        )
        await _sync_inviter_level_rewards(
            db_session,
            inviter_global_id=await _global_id_for_tg(
                db_session, INVITER_TG
            ),
        )
        await db_session.commit()
        actual_bonus = await _scalar_decimal(
            db_session,
            "SELECT bonus_balance FROM efhc_core.users "
            "WHERE global_id = :global_id",
            {
                "global_id": await _global_id_for_tg(
                    db_session, INVITER_TG
                )
            },
        )
        actual_logs = (
            await db_session.execute(
                text(
                    "SELECT COUNT(*) FROM efhc_core.efhc_transfers_log "
                    "WHERE global_id = :global_id "
                    "AND reason = 'referral_level_bonus'"
                ),
                {
                    "global_id": await _global_id_for_tg(
                        db_session, INVITER_TG
                    )
                },
            )
        ).scalar_one()
        assert actual_bonus == expected_bonus
        assert int(actual_logs) == expected_logs
        await _sync_inviter_level_rewards(
            db_session,
            inviter_global_id=await _global_id_for_tg(
                db_session, INVITER_TG
            ),
        )
        await db_session.commit()
        repeated = await _scalar_decimal(
            db_session,
            "SELECT bonus_balance FROM efhc_core.users "
            "WHERE global_id = :global_id",
            {
                "global_id": await _global_id_for_tg(
                    db_session, INVITER_TG
                )
            },
        )
        assert repeated == expected_bonus
        previous = threshold


async def test_direct_bonus_limit_and_query_plan_at_ten_thousand(
    db_session: AsyncSession,
) -> None:
    base = TG_BASE + 200_000
    await _create_user(db_session, tg_id=INVITER_TG)
    await _add_active_referrals(
        db_session,
        start_index=1,
        end_index=9_999,
        base_tg_id=base,
    )
    # Моделируем уже выданные номерные слоты 1..9998.
    # Ниже проверяется граница для 9999-го, 10000-го и 10001-го активного реферала.
    await db_session.execute(
        text(
            "UPDATE efhc_core.referral_links AS rl "
            "SET unit_reward_no = "
            "CAST(identity.provider_subject AS BIGINT) - :base_tg "
            "FROM efhc_core.user_identities AS identity "
            "WHERE rl.invitee_global_id = identity.global_id "
            "AND rl.inviter_global_id = :inviter_global_id "
            "AND identity.provider = 'telegram' "
            "AND identity.provider_tenant = 'default' "
            "AND CAST(identity.provider_subject AS BIGINT) "
            "BETWEEN :first_tg AND :last_tg"
        ),
        {
            "base_tg": base,
            "inviter_global_id": await _global_id_for_tg(
                db_session, INVITER_TG
            ),
            "first_tg": base + 1,
            "last_tg": base + 9_998,
        },
    )
    ref_9_999 = base + 9_999
    await _maybe_reward_active_unit_bonus(
        db_session,
        inviter_global_id=await _global_id_for_tg(
            db_session, INVITER_TG
        ),
        buyer_global_id=await _global_id_for_tg(
            db_session, ref_9_999
        ),
    )
    await db_session.commit()

    await _add_active_referrals(
        db_session,
        start_index=10_000,
        end_index=10_000,
        base_tg_id=base,
    )
    ref_10_000 = base + 10_000
    await _maybe_reward_active_unit_bonus(
        db_session,
        inviter_global_id=await _global_id_for_tg(
            db_session, INVITER_TG
        ),
        buyer_global_id=await _global_id_for_tg(
            db_session, ref_10_000
        ),
    )
    await db_session.commit()

    await _add_active_referrals(
        db_session,
        start_index=10_001,
        end_index=10_001,
        base_tg_id=base,
    )
    ref_10_001 = base + 10_001
    await _maybe_reward_active_unit_bonus(
        db_session,
        inviter_global_id=await _global_id_for_tg(
            db_session, INVITER_TG
        ),
        buyer_global_id=await _global_id_for_tg(
            db_session, ref_10_001
        ),
    )
    await db_session.commit()

    keys = (
        await db_session.execute(
            text(
                "SELECT idempotency_key "
                "FROM efhc_core.efhc_transfers_log "
                "WHERE global_id = :global_id "
                "AND reason = 'referral_active_unit' "
                "ORDER BY id"
            ),
            {
                "global_id": await _global_id_for_tg(
                    db_session, INVITER_TG
                )
            },
        )
    ).scalars().all()
    inviter_global_id = await _global_id_for_tg(db_session, INVITER_TG)
    assert keys == [
        f"REF_ACT_UNIT:G{inviter_global_id:010d}:N09999",
        f"REF_ACT_UNIT:G{inviter_global_id:010d}:N10000",
    ]

    inviter_global_id = await _global_id_for_tg(
        db_session, INVITER_TG
    )
    await db_session.execute(text("SET LOCAL enable_seqscan = off"))
    for want_active in (True, False):
        plan = (
            await db_session.execute(
                text(
                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                    + SQL_LIST_REFERRALS_GLOBAL
                ),
                {
                    "inviter_global_id": inviter_global_id,
                    "cursor_ts": None,
                    "cursor_id": None,
                    "want_active": want_active,
                    "fetch_limit": 51,
                },
            )
        ).scalar_one()
        plan_text = str(plan)
        index_names = _plan_index_names(plan)
        assert "Limit" in plan_text
        referral_nodes = [
            node
            for node in _walk_plan_nodes(plan)
            if node.get("Relation Name") == "referral_links"
        ]
        assert referral_nodes
        assert any(
            "Index" in str(node.get("Node Type", ""))
            or "Bitmap" in str(node.get("Node Type", ""))
            for node in referral_nodes
        ), referral_nodes
        assert index_names & PANEL_QUERY_INDEXES, (
            "referral list must use a panels.global_id index; "
            f"selected indexes={sorted(index_names)}"
        )


async def test_admin_summary_and_global_crud_use_current_truth(
    db_session: AsyncSession,
) -> None:
    await _create_user(db_session, tg_id=INVITER_TG)
    await _create_user(db_session, tg_id=INVITEE_TG)
    await _create_user(db_session, tg_id=INVITEE_TG + 1)
    await _create_referral_link(
        db_session,
        invitee_tg_id=INVITEE_TG,
    )
    await _create_referral_link(
        db_session,
        invitee_tg_id=INVITEE_TG + 1,
    )
    activated = await activate_referral(
        db_session,
        invitee_global_id=await _global_id_for_tg(
            db_session, INVITEE_TG
        ),
    )
    await db_session.execute(
        text(
            """
            INSERT INTO efhc_core.efhc_transfers_log (
                global_id, tg_id, amount, direction, balance_type,
                reason, idempotency_key, meta
            )
            VALUES
                (:global_id, :tg, 0.1, 'credit', 'bonus',
                 'referral_active_unit', 'IT:ADMIN:UNIT', '{}'),
                (:global_id, :tg, 10, 'credit', 'bonus',
                 'referral_level_bonus', 'IT:ADMIN:LEVEL', '{}')
            """
        ),
        {
            "global_id": await _global_id_for_tg(
                db_session, INVITER_TG
            ),
            "tg": INVITER_TG,
        },
    )
    await db_session.commit()
    assert activated.activated_now is True
    assert activated.link is not None
    assert activated.link.activated_at is not None
    active_items, _ = await list_active_refs_cursor(
        db_session,
        inviter_global_id=await _global_id_for_tg(
            db_session, INVITER_TG
        ),
        limit=10,
    )
    inactive_items, _ = await list_inactive_refs_cursor(
        db_session,
        inviter_global_id=await _global_id_for_tg(
            db_session, INVITER_TG
        ),
        limit=10,
    )
    total, active = await count_total_and_active(
        db_session,
        inviter_global_id=await _global_id_for_tg(
            db_session, INVITER_TG
        ),
    )
    summary = await admin_summary(db_session, limit=10)
    top = await admin_top_inviters(db_session, limit=10)
    assert [item.invitee_global_id for item in active_items] == [
        await _global_id_for_tg(db_session, INVITEE_TG)
    ]
    assert [item.invitee_global_id for item in inactive_items] == [
        await _global_id_for_tg(db_session, INVITEE_TG + 1)
    ]
    assert (total, active) == (2, 1)
    assert Decimal(summary["items"][0]["total_bonus_efhc"]) == Decimal(
        "10.10000000"
    )
    assert len(top) >= 1
