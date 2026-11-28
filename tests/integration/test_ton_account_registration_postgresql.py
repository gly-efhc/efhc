"""Real PostgreSQL TON account registration tests цикла 1617."""

from __future__ import annotations

import asyncio
import hashlib
import itertools
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.identity.auth_provider import AuthProvider
from app.identity.provider_registry import (
    finalize_verified_provider_subject,
)
from app.identity.ton_account_registration import (
    TonAccountRegistrationError,
    TonAccountRegistrationService,
)
from app.identity.ton_proof_verification import VerifiedTonProof
from app.models.identity_models import UserIdentity
from app.models.user_models import User
from app.models.wallets_models import WalletBinding
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("db_clean")]
_TG_IDS = itertools.count(8_970_000_000_000)


def _subject(label: str) -> str:
    digest = hashlib.sha256(
        f"{label}:{uuid4()}".encode("ascii")
    ).hexdigest()
    return f"0:{digest}"


def _proof(subject: str) -> VerifiedTonProof:
    return VerifiedTonProof(
        challenge_id=uuid4(),
        verified_identity=finalize_verified_provider_subject(
            AuthProvider.TON,
            subject,
        ),
        network="mainnet",
        verified_at=datetime.now(UTC),
        key_source="integration_fixture",
    )


async def _create_user(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    tg_id: int | None = None,
) -> int:
    _ = tg_id  # provider metadata не хранится в users
    async with session_factory() as session, session.begin():
        user = User()
        session.add(user)
        await session.flush()
        assert user.global_id is not None
        return int(user.global_id)


async def _create_identity(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    global_id: int,
    subject: str,
) -> None:
    async with session_factory() as session, session.begin():
        session.add(
            UserIdentity(
                global_id=global_id,
                provider=AuthProvider.TON.value,
                provider_tenant="default",
                provider_subject=subject,
                status="active",
                is_primary=True,
                is_verified=True,
                verified_at=datetime.now(UTC),
            )
        )


async def _create_binding(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    subject: str,
    tg_id: int | None = None,
    global_id: int | None = None,
    verified: bool = True,
) -> None:
    async with session_factory() as session, session.begin():
        session.add(
            WalletBinding(
                global_id=global_id,
                tg_id=tg_id,
                wallet_address=subject,
                is_primary=True,
                is_active=True,
                proof_verified=verified,
                proof_verified_at=(
                    datetime.now(UTC) if verified else None
                ),
                proof_source="integration_fixture",
            )
        )


async def test_existing_ton_identity_возвращает_тот_же_global_id(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    subject = _subject("existing")
    global_id = await _create_user(
        integration_session_factory,
        tg_id=next(_TG_IDS),
    )
    await _create_identity(
        integration_session_factory,
        global_id=global_id,
        subject=subject,
    )

    result = await TonAccountRegistrationService(
        integration_session_factory
    ).register_or_resolve(_proof(subject))

    assert result.global_id.value == global_id
    assert result.outcome == "existing_identity"
    async with integration_session_factory() as session:
        binding = await session.scalar(
            select(WalletBinding).where(
                WalletBinding.wallet_address == subject
            )
        )
        assert binding is not None
        assert binding.global_id == global_id


async def test_verified_binding_создаёт_identity_того_же_account(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    subject = _subject("legacy")
    telegram_subject = next(_TG_IDS)
    global_id = await _create_user(
        integration_session_factory,
        tg_id=telegram_subject,
    )
    await _create_binding(
        integration_session_factory,
        subject=subject,
        tg_id=telegram_subject,
        global_id=global_id,
    )

    result = await TonAccountRegistrationService(
        integration_session_factory
    ).register_or_resolve(_proof(subject))

    assert result.global_id.value == global_id
    assert result.outcome == "existing_binding"
    async with integration_session_factory() as session:
        identity = await session.scalar(
            select(UserIdentity).where(
                UserIdentity.provider_subject == subject
            )
        )
        binding = await session.scalar(
            select(WalletBinding).where(
                WalletBinding.wallet_address == subject
            )
        )
        assert identity is not None
        assert identity.global_id == global_id
        assert binding is not None
        assert binding.global_id == global_id


async def test_new_wallet_создаёт_ton_only_account_без_fake_tg_id(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    subject = _subject("new")
    result = await TonAccountRegistrationService(
        integration_session_factory
    ).register_or_resolve(_proof(subject))

    assert result.outcome == "registered"
    async with integration_session_factory() as session:
        user = await session.scalar(
            select(User).where(
                User.global_id == result.global_id.value
            )
        )
        identity = await session.scalar(
            select(UserIdentity).where(
                UserIdentity.provider_subject == subject
            )
        )
        binding = await session.scalar(
            select(WalletBinding).where(
                WalletBinding.wallet_address == subject
            )
        )
        telegram_identity = await session.scalar(
            select(UserIdentity).where(
                UserIdentity.global_id == result.global_id.value,
                UserIdentity.provider == AuthProvider.TELEGRAM.value,
            )
        )
        assert user is not None
        assert telegram_identity is None
        assert identity is not None
        assert identity.global_id == result.global_id.value
        assert binding is not None
        assert binding.global_id == result.global_id.value
        assert binding.tg_id is None


async def test_concurrent_registration_создаёт_один_global_account(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    subject = _subject("concurrent")
    service = TonAccountRegistrationService(integration_session_factory)

    results = await asyncio.gather(
        *(service.register_or_resolve(_proof(subject)) for _ in range(6))
    )

    assert len({item.global_id.value for item in results}) == 1
    assert sum(item.outcome == "registered" for item in results) == 1
    async with integration_session_factory() as session:
        identities = await session.scalar(
            select(func.count(UserIdentity.id)).where(
                UserIdentity.provider_subject == subject
            )
        )
        bindings = await session.scalar(
            select(func.count(WalletBinding.id)).where(
                WalletBinding.wallet_address == subject
            )
        )
        assert int(identities or 0) == 1
        assert int(bindings or 0) == 1


async def test_непроверенный_binding_завершается_закрыто(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    subject = _subject("unverified")
    telegram_subject = next(_TG_IDS)
    global_id = await _create_user(
        integration_session_factory,
        tg_id=telegram_subject,
    )
    await _create_binding(
        integration_session_factory,
        subject=subject,
        tg_id=telegram_subject,
        global_id=global_id,
        verified=False,
    )

    with pytest.raises(TonAccountRegistrationError) as captured:
        await TonAccountRegistrationService(
            integration_session_factory
        ).register_or_resolve(_proof(subject))
    assert captured.value.reason == "BINDING_UNVERIFIED"


async def test_ton_binding_линкуется_к_существующему_telegram_account(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    subject = _subject("telegram-link")
    telegram_subject = str(next(_TG_IDS))
    global_id = await _create_user(integration_session_factory)
    async with integration_session_factory() as session, session.begin():
        session.add(
            UserIdentity(
                global_id=global_id,
                provider=AuthProvider.TELEGRAM.value,
                provider_tenant="default",
                provider_subject=str(telegram_subject),
                status="active",
                is_primary=True,
                is_verified=True,
                verified_at=datetime.now(UTC),
            )
        )
    await _create_binding(
        integration_session_factory,
        subject=subject,
        global_id=global_id,
    )

    result = await TonAccountRegistrationService(
        integration_session_factory
    ).register_or_resolve(_proof(subject))

    assert result.global_id.value == global_id
    assert result.outcome == "existing_binding"
    async with integration_session_factory() as session:
        identities = list(
            await session.scalars(
                select(UserIdentity).where(
                    UserIdentity.global_id == global_id
                )
            )
        )
    assert {item.provider for item in identities} == {
        AuthProvider.TELEGRAM.value,
        AuthProvider.TON.value,
    }
    assert sum(item.is_primary is True for item in identities) == 1


async def test_ton_identity_и_wallet_binding_разных_accounts_дают_conflict(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    subject = _subject("owner-conflict")
    identity_global_id = await _create_user(
        integration_session_factory,
    )
    binding_global_id = await _create_user(
        integration_session_factory,
    )
    await _create_identity(
        integration_session_factory,
        global_id=identity_global_id,
        subject=subject,
    )
    await _create_binding(
        integration_session_factory,
        subject=subject,
        global_id=binding_global_id,
    )

    with pytest.raises(TonAccountRegistrationError) as captured:
        await TonAccountRegistrationService(
            integration_session_factory
        ).register_or_resolve(_proof(subject))

    assert captured.value.reason == "WALLET_IDENTITY_CONFLICT"
