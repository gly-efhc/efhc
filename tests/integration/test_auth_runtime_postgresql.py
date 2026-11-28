"""Real PostgreSQL tests auth-core цикла 1613."""

from __future__ import annotations

import asyncio
import itertools
from datetime import timedelta

import pytest
from app.identity import (
    AuthChallengeNotConsumable,
    AuthChallengeService,
    AuthProvider,
    AuthSessionNotActive,
    AuthSessionService,
    GlobalId,
    UserRoleService,
    hash_auth_challenge,
    hash_auth_session_token,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio
_TG_IDS = itertools.count(8_940_000_000_000)


async def _create_user_and_identity(
    session: AsyncSession,
) -> tuple[GlobalId, int]:
    global_id = int(
        (
            await session.execute(
                text(
                    "INSERT INTO efhc_core.users DEFAULT VALUES "
                    "RETURNING global_id"
                ),
            )
        ).scalar_one()
    )
    identity_id = int(
        (
            await session.execute(
                text(
                    "INSERT INTO efhc_core.user_identities ("
                    "global_id, provider, provider_tenant, "
                    "provider_subject, status, is_verified, verified_at"
                    ") VALUES ("
                    ":global_id, 'telegram', 'default', :subject, "
                    "'active', true, now()"
                    ") RETURNING id"
                ),
                {
                    "global_id": global_id,
                    "subject": f"telegram:auth-runtime:{global_id}",
                },
            )
        ).scalar_one()
    )
    await session.commit()
    return GlobalId.from_database(global_id), identity_id


async def test_challenge_хранится_только_как_hash_и_consumed_once(
    db_session: AsyncSession,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = AuthChallengeService(integration_session_factory)
    issued = await service.issue(
        provider=AuthProvider.TELEGRAM,
        purpose="login",
        domain="app.efhc.example",
        ttl=timedelta(minutes=5),
    )
    stored = (
        await db_session.execute(
            text(
                "SELECT challenge_hash FROM efhc_core.auth_challenges "
                "WHERE id=:id"
            ),
            {"id": issued.challenge_id},
        )
    ).scalar_one()
    assert stored == hash_auth_challenge(issued.token)
    assert stored != issued.token

    consumed = await service.consume(
        issued.token,
        provider=AuthProvider.TELEGRAM,
        purpose="login",
        domain="app.efhc.example",
    )
    assert consumed.challenge_id == issued.challenge_id
    with pytest.raises(AuthChallengeNotConsumable):
        await service.consume(
            issued.token,
            provider=AuthProvider.TELEGRAM,
            purpose="login",
            domain="app.efhc.example",
        )


async def test_concurrent_challenge_consume_имеет_одного_winner(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = AuthChallengeService(integration_session_factory)
    issued = await service.issue(
        provider=AuthProvider.TELEGRAM,
        purpose="login",
        domain="app.efhc.example",
        ttl=timedelta(minutes=5),
    )

    results = await asyncio.gather(
        *(
            service.consume(
                issued.token,
                provider=AuthProvider.TELEGRAM,
                purpose="login",
                domain="app.efhc.example",
            )
            for _ in range(6)
        ),
        return_exceptions=True,
    )
    assert sum(not isinstance(item, Exception) for item in results) == 1
    assert sum(
        isinstance(item, AuthChallengeNotConsumable)
        for item in results
    ) == 5


async def test_hashed_session_строит_context_и_roles_by_global_id(
    db_session: AsyncSession,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    global_id, identity_id = await _create_user_and_identity(db_session)
    roles = UserRoleService(integration_session_factory)
    sessions = AuthSessionService(integration_session_factory)
    await roles.grant(global_id, "user")
    await roles.grant(global_id, "admin.read", source="system")

    issued = await sessions.issue(
        global_id=global_id,
        identity_id=identity_id,
        ttl=timedelta(hours=8),
    )
    stored = (
        await db_session.execute(
            text(
                "SELECT token_hash FROM efhc_core.auth_sessions "
                "WHERE id=:id"
            ),
            {"id": issued.session_id},
        )
    ).scalar_one()
    assert stored == hash_auth_session_token(issued.token)
    assert stored != issued.token

    context = await sessions.authenticate(issued.token)
    assert context.global_id == global_id
    assert context.provider is AuthProvider.TELEGRAM
    assert context.roles == frozenset({"user", "admin.read"})
    assert context.session_id == str(issued.session_id)


async def test_session_revoke_завершается_fail_closed(
    db_session: AsyncSession,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    global_id, identity_id = await _create_user_and_identity(db_session)
    service = AuthSessionService(integration_session_factory)
    issued = await service.issue(
        global_id=global_id,
        identity_id=identity_id,
        ttl=timedelta(hours=1),
    )
    assert await service.revoke(issued.token) is True
    assert await service.revoke(issued.token) is False
    with pytest.raises(AuthSessionNotActive):
        await service.authenticate(issued.token)


async def test_session_identity_global_mismatch_запрещён(
    db_session: AsyncSession,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    first_global, _ = await _create_user_and_identity(db_session)
    _, second_identity = await _create_user_and_identity(db_session)
    service = AuthSessionService(integration_session_factory)
    with pytest.raises(AuthSessionNotActive):
        await service.issue(
            global_id=first_global,
            identity_id=second_identity,
            ttl=timedelta(hours=1),
        )


async def test_session_issue_отклоняет_unknown_storage_provider(
    db_session: AsyncSession,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    global_id = int(
        (
            await db_session.execute(
                text(
                    "INSERT INTO efhc_core.users DEFAULT VALUES "
                    "RETURNING global_id"
                ),
            )
        ).scalar_one()
    )
    identity_id = int(
        (
            await db_session.execute(
                text(
                    "INSERT INTO efhc_core.user_identities ("
                    "global_id, provider, provider_tenant, "
                    "provider_subject, status, is_verified, verified_at"
                    ") VALUES ("
                    ":global_id, 'unknown', 'default', :subject, "
                    "'active', true, now()"
                    ") RETURNING id"
                ),
                {
                    "global_id": global_id,
                    "subject": f"unknown:auth-runtime:{global_id}",
                },
            )
        ).scalar_one()
    )
    await db_session.commit()

    service = AuthSessionService(integration_session_factory)
    with pytest.raises(AuthSessionNotActive):
        await service.issue(
            global_id=GlobalId.from_database(global_id),
            identity_id=identity_id,
            ttl=timedelta(hours=1),
        )


async def test_role_revoke_удаляет_роль_из_new_auth_context(
    db_session: AsyncSession,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    global_id, identity_id = await _create_user_and_identity(db_session)
    roles = UserRoleService(integration_session_factory)
    sessions = AuthSessionService(integration_session_factory)
    await roles.grant(global_id, "user")
    issued = await sessions.issue(
        global_id=global_id,
        identity_id=identity_id,
        ttl=timedelta(hours=1),
    )
    assert (await sessions.authenticate(issued.token)).roles == frozenset(
        {"user"}
    )
    assert await roles.revoke(global_id, "user") is True
    assert (await sessions.authenticate(issued.token)).roles == frozenset()


async def test_auth_runtime_schema_head_0008_и_constraints_present(
    db_session: AsyncSession,
) -> None:
    revision = (
        await db_session.execute(
            text(
                "SELECT version_num "
                "FROM efhc_core.alembic_version"
            )
        )
    ).scalar_one()
    assert revision == "0001"

    tables = set(
        (
            await db_session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='efhc_core' "
                    "AND table_name IN "
                    "('auth_challenges','auth_sessions','user_roles')"
                )
            )
        ).scalars()
    )
    assert tables == {"auth_challenges", "auth_sessions", "user_roles"}

    constraints = set(
        (
            await db_session.execute(
                text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE connamespace='efhc_core'::regnamespace "
                    "AND conname IN ("
                    "'uq_user_identities_id_global_id',"
                    "'fk_auth_sessions_identity_global_user_identities',"
                    "'uq_auth_sessions_token_hash',"
                    "'uq_user_roles_global_id_role'"
                    ")"
                )
            )
        ).scalars()
    )
    assert constraints == {
        "uq_user_identities_id_global_id",
        "fk_auth_sessions_identity_global_user_identities",
        "uq_auth_sessions_token_hash",
        "uq_user_roles_global_id_role",
    }


async def test_concurrent_role_grant_оставляет_одну_active_role(
    db_session: AsyncSession,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    global_id, _ = await _create_user_and_identity(db_session)
    service = UserRoleService(integration_session_factory)
    await asyncio.gather(
        *(service.grant(global_id, "user") for _ in range(6))
    )
    count = int(
        (
            await db_session.execute(
                text(
                    "SELECT count(*) FROM efhc_core.user_roles "
                    "WHERE global_id=:global_id AND role='user' "
                    "AND status='active'"
                ),
                {"global_id": global_id.value},
            )
        ).scalar_one()
    )
    assert count == 1
