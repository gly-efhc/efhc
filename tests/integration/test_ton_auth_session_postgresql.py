"""Real PostgreSQL TON session/logout tests цикла 1618."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.identity.auth_errors import AuthSessionNotActive
from app.identity.auth_provider import AuthProvider
from app.identity.auth_runtime_services import (
    AuthSessionService,
    hash_auth_session_token,
)
from app.identity.provider_registry import (
    finalize_verified_provider_subject,
)
from app.identity.ton_auth_session import TonAuthSessionService
from app.identity.ton_proof_verification import VerifiedTonProof
from app.models.auth_models import AuthSession
from app.models.identity_models import UserIdentity
from app.models.user_models import User
from app.models.wallets_models import WalletBinding
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("db_clean")]


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


async def test_ton_only_login_выдаёт_hashed_session_без_tg_id(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    result = await TonAuthSessionService(
        integration_session_factory
    ).login(_proof(_subject("new-session")))

    context = await AuthSessionService(
        integration_session_factory
    ).authenticate(result.session.token)
    assert context.global_id == result.account.global_id
    assert context.provider is AuthProvider.TON

    async with integration_session_factory() as session:
        user = await session.scalar(
            select(User).where(
                User.global_id == result.account.global_id.value
            )
        )
        stored_hash = await session.scalar(
            select(AuthSession.token_hash).where(
                AuthSession.id == result.session.session_id
            )
        )
        telegram_identity = await session.scalar(
            select(UserIdentity).where(
                UserIdentity.global_id == result.account.global_id.value,
                UserIdentity.provider == AuthProvider.TELEGRAM.value,
            )
        )
    assert user is not None
    assert telegram_identity is None
    assert stored_hash == hash_auth_session_token(result.session.token)
    assert result.session.token != stored_hash


async def test_repeated_ton_login_возвращает_тот_же_account(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    subject = _subject("repeat-session")
    service = TonAuthSessionService(integration_session_factory)

    first = await service.login(_proof(subject))
    second = await service.login(_proof(subject))

    assert first.account.global_id == second.account.global_id
    assert first.session.token != second.session.token
    assert first.account.outcome == "registered"
    assert second.account.outcome == "existing_identity"


async def test_logout_отзывает_session_и_повторная_auth_закрыта(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    login = await TonAuthSessionService(
        integration_session_factory
    ).login(_proof(_subject("logout")))
    sessions = AuthSessionService(integration_session_factory)

    assert await sessions.revoke(login.session.token) is True
    assert await sessions.revoke(login.session.token) is False
    with pytest.raises(AuthSessionNotActive):
        await sessions.authenticate(login.session.token)


async def test_concurrent_ton_login_создаёт_один_account(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    subject = _subject("concurrent-session")
    service = TonAuthSessionService(integration_session_factory)

    results = await asyncio.gather(
        *(service.login(_proof(subject)) for _ in range(6))
    )
    global_ids = {item.account.global_id.value for item in results}
    assert len(global_ids) == 1
    assert len({item.session.token for item in results}) == 6

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
        accounts = await session.scalar(
            select(func.count(User.global_id)).where(
                User.global_id.in_(global_ids)
            )
        )
        auth_sessions = await session.scalar(
            select(func.count(AuthSession.id)).where(
                AuthSession.global_id.in_(global_ids)
            )
        )
    assert int(identities or 0) == 1
    assert int(bindings or 0) == 1
    assert int(accounts or 0) == 1
    assert int(auth_sessions or 0) == 6
