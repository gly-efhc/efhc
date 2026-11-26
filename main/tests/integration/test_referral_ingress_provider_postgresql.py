"""PostgreSQL-доказательства referral transport/callers циклов 1638–1639."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.identity.auth_provider import AuthProvider
from app.identity.provider_registry import (
    finalize_verified_provider_subject,
)
from app.identity.telegram_auth_session import (
    TelegramAuthSessionError,
    TelegramAuthSessionService,
)
from app.identity.telegram_init_data import TelegramInitDataAdapter
from app.identity.ton_account_registration import (
    TonAccountRegistrationError,
    TonAccountRegistrationService,
)
from app.identity.ton_proof_verification import VerifiedTonProof
from app.models.identity_models import UserIdentity
from app.models.referral_codes_models import ReferralCode
from app.models.referral_models import ReferralLink
from app.models.user_models import User
from app.models.wallets_models import WalletBinding
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.usefixtures("db_clean"),
]
NOW = datetime(2026, 8, 3, 0, 0, tzinfo=UTC)


def _telegram_verified(tg_id: int, label: str):
    received_hash = hashlib.sha256(label.encode("ascii")).hexdigest()
    payload = {
        "auth_date": str(int(NOW.timestamp())),
        "hash": received_hash,
        "user": {"id": tg_id},
    }
    adapter = TelegramInitDataAdapter(
        lambda _raw: payload,
        clock=lambda: NOW,
    )
    return adapter.verify(f"label={label}&hash={received_hash}")


def _ton_subject(label: str) -> str:
    digest = hashlib.sha256(
        f"{label}:{uuid4()}".encode("ascii")
    ).hexdigest()
    return f"0:{digest}"


def _ton_proof(subject: str) -> VerifiedTonProof:
    return VerifiedTonProof(
        challenge_id=uuid4(),
        verified_identity=finalize_verified_provider_subject(
            AuthProvider.TON,
            subject,
        ),
        network="mainnet",
        verified_at=NOW,
        key_source="referral_ingress_fixture",
    )


async def _create_referral_owner(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    tg_id: int,
    code: str,
) -> int:
    async with session_factory() as session, session.begin():
        inviter = User()
        session.add(inviter)
        await session.flush()
        assert inviter.global_id is not None
        global_id = int(inviter.global_id)
        session.add(
            UserIdentity(
                global_id=global_id,
                provider="telegram",
                provider_tenant="default",
                provider_subject=str(tg_id),
                status="active",
                is_primary=True,
                is_verified=True,
                verified_at=NOW,
            )
        )
        session.add(
            ReferralCode(
                code=code,
                inviter_global_id=global_id,
            )
        )
        return global_id


async def test_telegram_new_account_создаёт_referral_через_центр(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    inviter_global_id = await _create_referral_owner(
        integration_session_factory,
        tg_id=8_981_000_001,
        code="WEB1639A",
    )
    new_tg_id = 8_981_000_002

    result = await TelegramAuthSessionService(
        integration_session_factory
    ).login(
        _telegram_verified(new_tg_id, "telegram-referral-registered"),
        referral_start_param="WEB1639A",
    )

    assert result.account.outcome == "registered"
    async with integration_session_factory() as session:
        link = await session.scalar(
            select(ReferralLink).where(
                ReferralLink.invitee_global_id
                == result.account.global_id.value
            )
        )
        identity = await session.scalar(
            select(UserIdentity).where(
                UserIdentity.provider_subject == str(new_tg_id)
            )
        )
    assert link is not None
    assert link.inviter_global_id == inviter_global_id
    assert link.invitee_global_id == result.account.global_id.value
    assert identity is not None
    assert identity.global_id == result.account.global_id.value


async def test_telegram_new_account_отклоняет_missing_referral(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    new_tg_id = 8_981_000_003
    with pytest.raises(TelegramAuthSessionError) as captured:
        await TelegramAuthSessionService(
            integration_session_factory
        ).login(
            _telegram_verified(new_tg_id, "telegram-referral-missing"),
            referral_start_param="MISS1639",
        )

    assert captured.value.reason == "REFERRAL_CODE_NOT_FOUND"
    async with integration_session_factory() as session:
        users = await session.scalar(
            select(func.count(UserIdentity.id)).where(
                UserIdentity.provider == "telegram",
                UserIdentity.provider_subject == str(new_tg_id),
            )
        )
        identities = await session.scalar(
            select(func.count(UserIdentity.id)).where(
                UserIdentity.provider_subject == str(new_tg_id)
            )
        )
    assert int(users or 0) == 0
    assert int(identities or 0) == 0


async def test_existing_telegram_account_игнорирует_late_binding(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tg_id = 8_981_000_004
    async with integration_session_factory() as session, session.begin():
        user = User()
        session.add(user)
        await session.flush()
        session.add(
            UserIdentity(
                global_id=int(user.global_id),
                provider=AuthProvider.TELEGRAM.value,
                provider_tenant="default",
                provider_subject=str(tg_id),
                status="active",
                is_primary=True,
                is_verified=True,
                verified_at=NOW,
            )
        )

    result = await TelegramAuthSessionService(
        integration_session_factory
    ).login(
        _telegram_verified(tg_id, "telegram-existing-ignore"),
        referral_start_param="MISS1639",
    )
    assert result.account.outcome == "existing_identity"
    async with integration_session_factory() as session:
        links = await session.scalar(select(func.count(ReferralLink.id)))
    assert int(links or 0) == 0


async def test_ton_new_account_создаёт_referral_без_fake_tg_id(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    inviter_global_id = await _create_referral_owner(
        integration_session_factory,
        tg_id=8_981_000_005,
        code="TON1639A",
    )
    subject = _ton_subject("ton-referral-registered")

    result = await TonAccountRegistrationService(
        integration_session_factory
    ).register_or_resolve(
        _ton_proof(subject),
        referral_start_param="TON1639A",
    )

    assert result.outcome == "registered"
    async with integration_session_factory() as session:
        user = await session.scalar(
            select(User).where(User.global_id == result.global_id.value)
        )
        link = await session.scalar(
            select(ReferralLink).where(
                ReferralLink.invitee_global_id == result.global_id.value
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
    assert link is not None
    assert link.inviter_global_id == inviter_global_id
    assert link.invitee_global_id == result.global_id.value
    assert identity is not None
    assert binding is not None


async def test_ton_new_account_отклоняет_missing_referral_атомарно(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    subject = _ton_subject("ton-referral-missing")
    async with integration_session_factory() as session:
        users_before = int(
            await session.scalar(select(func.count(User.global_id))) or 0
        )

    with pytest.raises(TonAccountRegistrationError) as captured:
        await TonAccountRegistrationService(
            integration_session_factory
        ).register_or_resolve(
            _ton_proof(subject),
            referral_start_param="MISS1639",
        )

    assert captured.value.reason == "REFERRAL_CODE_NOT_FOUND"
    async with integration_session_factory() as session:
        users_after = int(
            await session.scalar(select(func.count(User.global_id))) or 0
        )
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
    assert users_after == users_before
    assert int(identities or 0) == 0
    assert int(bindings or 0) == 0
