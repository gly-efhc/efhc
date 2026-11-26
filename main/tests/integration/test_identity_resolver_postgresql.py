"""Real PostgreSQL tests transactional IdentityResolver цикла 1612."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from app.identity import (
    AuthProvider,
    AuthProviderRegistry,
    IdentityConflictCode,
    IdentityResolutionStatus,
    PostgreSQLIdentityResolver,
    ProviderAvailability,
    ProviderCapability,
    ProviderRegistration,
    VerifiedIdentity,
)
from app.identity.identity_resolver import _identity_advisory_lock_key
from app.identity.provider_registry import (
    finalize_verified_provider_subject,
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


class _TelegramTestAdapter:
    """Test-only verification adapter с production wire provider."""

    provider = AuthProvider.TELEGRAM

    def verify_subject(self, raw_input: object) -> str | None:
        if not isinstance(raw_input, dict):
            return None
        if raw_input.get("verified") is not True:
            return None
        subject = raw_input.get("subject")
        return subject if isinstance(subject, str) else None


def _identity(subject: str) -> VerifiedIdentity:
    registry = AuthProviderRegistry(environment="ci")
    registry.register(
        ProviderRegistration(
            provider=AuthProvider.TELEGRAM,
            canonical_name=AuthProvider.TELEGRAM.value,
            availability=ProviderAvailability.ENABLED,
            capabilities=frozenset(
                {ProviderCapability.VERIFY_IDENTITY}
            ),
            adapter_factory=_TelegramTestAdapter,
            test_only=True,
        )
    )
    return registry.verify(
        AuthProvider.TELEGRAM,
        {"verified": True, "subject": subject},
    )


async def _create_user(
    session: AsyncSession,
) -> int:
    result = await session.execute(
        text(
            """
            INSERT INTO efhc_core.users DEFAULT VALUES
            RETURNING global_id
            """
        ),
    )
    global_id = result.scalar_one()
    await session.commit()
    return int(global_id)


async def _bind_identity(
    session: AsyncSession,
    *,
    global_id: int,
    subject: str,
    provider: AuthProvider = AuthProvider.TELEGRAM,
    status: str = "active",
    verified: bool = True,
) -> None:
    verified_at = (
        datetime.now(UTC) if verified else None
    )
    await session.execute(
        text(
            """
            INSERT INTO efhc_core.user_identities (
                global_id,
                provider,
                provider_tenant,
                provider_subject,
                status,
                is_verified,
                verified_at
            ) VALUES (
                :global_id,
                :provider,
                'default',
                :subject,
                :status,
                :verified,
                :verified_at
            )
            """
        ),
        {
            "global_id": global_id,
            "provider": provider.value,
            "subject": subject,
            "status": status,
            "verified": verified,
            "verified_at": verified_at,
        },
    )
    await session.commit()


async def _counts(session: AsyncSession) -> tuple[int, int]:
    users = int(
        (
            await session.execute(
                text("SELECT count(*) FROM efhc_core.users")
            )
        ).scalar_one()
    )
    identities = int(
        (
            await session.execute(
                text(
                    "SELECT count(*) "
                    "FROM efhc_core.user_identities"
                )
            )
        ).scalar_one()
    )
    return users, identities


async def test_existing_identity_разрешается_без_mutation(
    db_session: AsyncSession,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    subject = "telegram:resolver:existing"
    global_id = await _create_user(db_session)
    await _bind_identity(
        db_session,
        global_id=global_id,
        subject=subject,
    )
    before = await _counts(db_session)
    resolver = PostgreSQLIdentityResolver(
        integration_session_factory
    )

    result = await resolver.resolve_verified_identity(
        _identity(subject)
    )

    assert result.status is IdentityResolutionStatus.RESOLVED
    assert result.global_id is not None
    assert result.global_id.value == global_id
    assert result.conflict_code is None
    assert await _counts(db_session) == before


async def test_missing_identity_возвращает_not_found_без_create(
    db_session: AsyncSession,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    before = await _counts(db_session)
    resolver = PostgreSQLIdentityResolver(
        integration_session_factory
    )

    result = await resolver.resolve_verified_identity(
        _identity("telegram:resolver:missing")
    )

    assert result.status is IdentityResolutionStatus.NOT_FOUND
    assert result.global_id is None
    assert result.conflict_code is None
    assert await _counts(db_session) == before


@pytest.mark.parametrize(
    ("status", "verified", "expected"),
    [
        (
            "disabled",
            True,
            IdentityConflictCode.IDENTITY_INACTIVE,
        ),
        (
            "revoked",
            True,
            IdentityConflictCode.IDENTITY_INACTIVE,
        ),
        (
            "active",
            False,
            IdentityConflictCode.IDENTITY_UNVERIFIED,
        ),
    ],
)
async def test_ineligible_identity_возвращает_conflict(
    db_session: AsyncSession,
    integration_session_factory: async_sessionmaker[AsyncSession],
    status: str,
    verified: bool,
    expected: IdentityConflictCode,
) -> None:
    subject = f"telegram:resolver:{status}:{verified}"
    global_id = await _create_user(db_session)
    await _bind_identity(
        db_session,
        global_id=global_id,
        subject=subject,
        status=status,
        verified=verified,
    )
    resolver = PostgreSQLIdentityResolver(
        integration_session_factory
    )

    result = await resolver.resolve_verified_identity(
        _identity(subject)
    )

    assert result.status is IdentityResolutionStatus.CONFLICT
    assert result.global_id is None
    assert result.conflict_code is expected


async def test_concurrent_resolve_детерминирован(
    db_session: AsyncSession,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    subject = "telegram:resolver:concurrent"
    global_id = await _create_user(db_session)
    await _bind_identity(
        db_session,
        global_id=global_id,
        subject=subject,
    )
    before = await _counts(db_session)
    resolver = PostgreSQLIdentityResolver(
        integration_session_factory
    )
    identity = _identity(subject)

    results = await asyncio.gather(
        *(resolver.resolve_verified_identity(identity) for _ in range(6))
    )

    assert {
        (result.status, result.global_id, result.conflict_code)
        for result in results
    } == {
        (
            IdentityResolutionStatus.RESOLVED,
            results[0].global_id,
            None,
        )
    }
    assert results[0].global_id is not None
    assert results[0].global_id.value == global_id
    assert await _counts(db_session) == before


async def test_advisory_lock_сериализует_missing_row_lookup(
    db_session: AsyncSession,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _ = db_session
    subject = "telegram:resolver:advisory-lock"
    identity = _identity(subject)
    resolver = PostgreSQLIdentityResolver(
        integration_session_factory
    )
    lock_key = _identity_advisory_lock_key(
        provider=AuthProvider.TELEGRAM,
        provider_tenant="default",
        provider_subject=subject,
    )

    async with (
        integration_session_factory() as blocker,
        blocker.begin(),
    ):
        await blocker.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": lock_key},
        )
        task = asyncio.create_task(
            resolver.resolve_verified_identity(identity)
        )
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(
                asyncio.shield(task),
                timeout=0.25,
            )
    result = await asyncio.wait_for(task, timeout=2.0)

    assert result.status is IdentityResolutionStatus.NOT_FOUND


async def test_resolve_in_transaction_не_commit_caller_scope(
    db_session: AsyncSession,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    subject = "telegram:resolver:caller-transaction"
    global_id = await _create_user(db_session)
    await _bind_identity(
        db_session,
        global_id=global_id,
        subject=subject,
    )
    resolver = PostgreSQLIdentityResolver(
        integration_session_factory
    )

    async with (
        integration_session_factory() as session,
        session.begin(),
    ):
        result = await resolver.resolve_in_transaction(
            session,
            _identity(subject),
        )
        assert session.in_transaction()
        assert result.global_id is not None
        assert result.global_id.value == global_id


async def test_одинаковый_subject_разных_provider_разрешается_раздельно(
    db_session: AsyncSession,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    subject = "0:" + "17" * 32
    telegram_global_id = await _create_user(db_session)
    ton_global_id = await _create_user(db_session)
    await _bind_identity(
        db_session,
        global_id=telegram_global_id,
        subject=subject,
        provider=AuthProvider.TELEGRAM,
    )
    await _bind_identity(
        db_session,
        global_id=ton_global_id,
        subject=subject,
        provider=AuthProvider.TON,
    )
    resolver = PostgreSQLIdentityResolver(integration_session_factory)

    telegram = await resolver.resolve_verified_identity(
        finalize_verified_provider_subject(
            AuthProvider.TELEGRAM,
            subject,
        )
    )
    ton = await resolver.resolve_verified_identity(
        finalize_verified_provider_subject(
            AuthProvider.TON,
            subject,
        )
    )

    assert telegram.status is IdentityResolutionStatus.RESOLVED
    assert ton.status is IdentityResolutionStatus.RESOLVED
    assert telegram.global_id is not None
    assert ton.global_id is not None
    assert telegram.global_id.value == telegram_global_id
    assert ton.global_id.value == ton_global_id
    assert telegram.global_id != ton.global_id


async def test_одна_provider_subject_пара_не_может_принадлежать_двум_accounts(
    db_session: AsyncSession,
) -> None:
    subject = "telegram:resolver:unique-pair"
    first_global_id = await _create_user(db_session)
    second_global_id = await _create_user(db_session)
    await _bind_identity(
        db_session,
        global_id=first_global_id,
        subject=subject,
    )

    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                """
                INSERT INTO efhc_core.user_identities (
                    global_id, provider, provider_tenant,
                    provider_subject, status, is_verified, verified_at
                ) VALUES (
                    :global_id, 'telegram', 'default',
                    :subject, 'active', true, :verified_at
                )
                """
            ),
            {
                "global_id": second_global_id,
                "subject": subject,
                "verified_at": datetime.now(UTC),
            },
        )
        await db_session.commit()
    await db_session.rollback()
