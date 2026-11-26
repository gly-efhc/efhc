"""Authenticated referral API proof on the real PostgreSQL schema."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from app.deps import get_db
from app.identity.nonfinancial_owner import (
    resolve_nonfinancial_read_owner,
)
from app.identity.nonfinancial_read_dependency import (
    get_nonfinancial_read_owner,
)
from app.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

INVITER_TG = 8_842_000_000_000
OTHER_INVITER_TG = INVITER_TG + 100
ACTIVE_1 = INVITER_TG + 1
ACTIVE_2 = INVITER_TG + 2
INACTIVE_1 = INVITER_TG + 3


async def _global_id_for_tg(db: AsyncSession, tg_id: int) -> int:
    value = (
        await db.execute(
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
    return int(value)


async def _insert_user_identity(
    db: AsyncSession, *, tg_id: int, username: str
) -> int:
    global_id = int(
        (
            await db.execute(
                text(
                    "INSERT INTO efhc_core.users "
                    "(username, main_balance, bonus_balance, is_active) "
                    "VALUES (:username, 0, 0, TRUE) RETURNING global_id"
                ),
                {"username": username},
            )
        ).scalar_one()
    )
    await db.execute(
        text(
            "INSERT INTO efhc_core.user_identities ("
            "global_id, provider, provider_tenant, provider_subject, "
            "status, is_primary, is_verified, verified_at"
            ") VALUES ("
            ":global_id, 'telegram', 'default', :subject, "
            "'active', TRUE, TRUE, now()"
            ")"
        ),
        {"global_id": global_id, "subject": str(int(tg_id))},
    )
    return global_id


async def _seed_api_data(db: AsyncSession) -> None:
    for tg_id, username in (
        (INVITER_TG, "inviter"),
        (OTHER_INVITER_TG, "other"),
        (ACTIVE_1, "active_1"),
        (ACTIVE_2, "active_2"),
        (INACTIVE_1, "inactive_1"),
    ):
        await _insert_user_identity(db, tg_id=tg_id, username=username)
    inviter_global = await _global_id_for_tg(db, INVITER_TG)
    active_1_global = await _global_id_for_tg(db, ACTIVE_1)
    active_2_global = await _global_id_for_tg(db, ACTIVE_2)
    inactive_1_global = await _global_id_for_tg(db, INACTIVE_1)
    shared_time = datetime.now(UTC) - timedelta(minutes=2)
    await db.execute(
        text(
            """
            INSERT INTO efhc_core.referral_links (
                inviter_global_id, invitee_global_id,
                created_at, activated_at
            )
            VALUES
                (:inviter_global, :active1_global,
                 :shared_time, :shared_time),
                (:inviter_global, :active2_global,
                 :shared_time, :shared_time),
                (:inviter_global, :inactive1_global,
                 :inactive_time, NULL)
            """
        ),
        {
            "inviter_global": inviter_global,
            "active1_global": active_1_global,
            "active2_global": active_2_global,
            "inactive1_global": inactive_1_global,
            "shared_time": shared_time,
            "inactive_time": shared_time + timedelta(minutes=1),
        },
    )
    await db.execute(
        text(
            """
            INSERT INTO efhc_core.panels (
                global_id, public_id, is_active, is_archived,
                activated_at, expires_at, archived_at,
                last_generated_at, base_gen_per_sec, generated_kwh
            )
            VALUES
                (:active1_global, 'ITAPI00000001', TRUE, FALSE,
                 NOW(), NOW() + INTERVAL '180 days', NULL,
                 NOW(), 0, 0),
                (:active2_global, 'ITAPI00000002', FALSE, TRUE,
                 NOW(), NOW() + INTERVAL '180 days', NOW(),
                 NOW(), 0, 0)
            """
        ),
        {
            "active1_global": active_1_global,
            "active2_global": active_2_global,
        },
    )
    await db.commit()


@asynccontextmanager
async def _client_for_user(
    *,
    db: AsyncSession,
    tg_id: int,
) -> AsyncIterator[AsyncClient]:
    async def override_db() -> AsyncIterator[AsyncSession]:
        yield db

    async def override_owner():
        global_id = await _global_id_for_tg(db, int(tg_id))
        return await resolve_nonfinancial_read_owner(
            db,
            global_id=global_id,
        )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_nonfinancial_read_owner] = (
        override_owner
    )
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


async def test_active_inactive_cursor_and_archive_semantics(
    db_session: AsyncSession,
) -> None:
    await _seed_api_data(db_session)
    async with _client_for_user(db=db_session, tg_id=INVITER_TG) as client:
        first = await client.get(
            "/api/referrals/active/me",
            params={"limit": 1},
        )
        assert first.status_code == 200
        first_payload = first.json()
        assert [item["global_id"] for item in first_payload["items"]] == [
            f"{await _global_id_for_tg(db_session, ACTIVE_2):010d}"
        ]
        assert first_payload["items"][0]["is_active"] is True
        assert first_payload["next_cursor"]

        second = await client.get(
            "/api/referrals/active/me",
            params={
                "limit": 1,
                "cursor": first_payload["next_cursor"],
            },
        )
        assert second.status_code == 200
        second_payload = second.json()
        assert [item["global_id"] for item in second_payload["items"]] == [
            f"{await _global_id_for_tg(db_session, ACTIVE_1):010d}"
        ]
        assert second_payload["next_cursor"] is None
        assert set(
            item["global_id"]
            for item in first_payload["items"] + second_payload["items"]
        ) == {
            f"{await _global_id_for_tg(db_session, ACTIVE_1):010d}",
            f"{await _global_id_for_tg(db_session, ACTIVE_2):010d}",
        }

        inactive = await client.get(
            "/api/referrals/inactive/me",
            params={"limit": 10},
        )
        assert inactive.status_code == 200
        payload = inactive.json()
        assert [item["global_id"] for item in payload["items"]] == [
            f"{await _global_id_for_tg(db_session, INACTIVE_1):010d}"
        ]
        assert payload["items"][0]["panels_count"] == 0


async def test_etag_returns_304_and_changes_after_dataset_mutation(
    db_session: AsyncSession,
) -> None:
    await _seed_api_data(db_session)
    async with _client_for_user(db=db_session, tg_id=INVITER_TG) as client:
        first = await client.get(
            "/api/referrals/inactive/me",
            params={"limit": 10},
        )
        assert first.status_code == 200
        old_etag = first.headers["etag"]
        repeated = await client.get(
            "/api/referrals/inactive/me",
            params={"limit": 10},
            headers={"If-None-Match": old_etag},
        )
        assert repeated.status_code == 304
        assert repeated.headers["etag"] == old_etag

        new_tg = INVITER_TG + 4
        new_global = await _insert_user_identity(
            db_session, tg_id=new_tg, username="new_inactive"
        )
        inviter_global = await _global_id_for_tg(db_session, INVITER_TG)
        await db_session.execute(
            text(
                "INSERT INTO efhc_core.referral_links "
                "(inviter_global_id, invitee_global_id, created_at) "
                "VALUES (:inviter_global, :invitee_global, NOW())"
            ),
            {
                "inviter_global": inviter_global,
                "invitee_global": new_global,
            },
        )
        await db_session.commit()

        changed = await client.get(
            "/api/referrals/inactive/me",
            params={"limit": 10},
            headers={"If-None-Match": old_etag},
        )
        assert changed.status_code == 200
        assert changed.headers["etag"] != old_etag
        assert f"{new_global:010d}" in [
            item["global_id"] for item in changed.json()["items"]
        ]


async def test_legacy_owner_routes_removed(
    db_session: AsyncSession,
) -> None:
    await _seed_api_data(db_session)
    async with _client_for_user(db=db_session, tg_id=INVITER_TG) as client:
        for path in (
            "/api/referrals/stats",
            "/api/referrals/counters",
            "/api/referrals/active",
            "/api/referrals/inactive",
        ):
            response = await client.get(
                path,
                params={"parent_tg_id": INVITER_TG},
            )
            assert response.status_code == 404


async def test_me_routes_never_accept_another_owner(
    db_session: AsyncSession,
) -> None:
    await _seed_api_data(db_session)
    async with _client_for_user(db=db_session, tg_id=INVITER_TG) as client:
        stats = await client.get(
            "/api/referrals/stats/me",
            params={"parent_tg_id": OTHER_INVITER_TG},
        )
        counters = await client.get(
            "/api/referrals/counters/me",
            params={"parent_tg_id": OTHER_INVITER_TG},
        )
        assert stats.status_code == 200
        assert counters.status_code == 200
        assert stats.json()["total_referrals"] == 3
        assert counters.json() == {"total": 3, "active": 2, "inactive": 1}
