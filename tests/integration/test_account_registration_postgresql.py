"""Реальные PostgreSQL-контракты общего ядра регистрации."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from app.identity.account_registration import (
    AccountRegistrationError,
    NewAccountRequest,
    create_new_account,
)
from app.identity.auth_provider import AuthProvider
from app.models.identity_models import UserIdentity
from app.models.referral_codes_models import ReferralCode
from app.models.referral_models import ReferralLink
from app.models.user_models import User
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.usefixtures("db_clean"),
]


async def _create_inviter(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    tg_id: int,
    code: str,
) -> int:
    async with session_factory() as session, session.begin():
        inviter = User(username="inviter")
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
                verified_at=datetime.now(UTC),
            )
        )
        session.add(
            ReferralCode(
                code=code,
                inviter_global_id=global_id,
            )
        )
        return global_id


async def _count_users(
    session_factory: async_sessionmaker[AsyncSession],
) -> int:
    async with session_factory() as session:
        return int(await session.scalar(select(func.count(User.global_id))) or 0)


async def test_telegram_account_без_кода_создаётся_как_zero_user(
    integration_session_factory: async_sessionmaker[AsyncSession],
    next_referral_tg_id: Callable[[], int],
) -> None:
    tg_id = next_referral_tg_id()
    async with (
        integration_session_factory() as session,
        session.begin(),
    ):
        result = await create_new_account(
            session,
            NewAccountRequest(
                provider=AuthProvider.TELEGRAM,
                tg_id=tg_id,
                username="zero_user",
            ),
        )

    assert result.tg_id == tg_id
    assert result.referral_attached is False
    assert result.referral_reason == "no_code"
    async with integration_session_factory() as session:
        user = await session.scalar(
            select(User).where(User.global_id == result.global_id.value)
        )
        links = await session.scalar(select(func.count(ReferralLink.id)))
        assert user is not None
        assert user.username == "zero_user"
        assert int(links or 0) == 0


async def test_валидный_referral_создаётся_в_той_же_транзакции(
    integration_session_factory: async_sessionmaker[AsyncSession],
    next_referral_tg_id: Callable[[], int],
) -> None:
    inviter_tg_id = next_referral_tg_id()
    invitee_tg_id = next_referral_tg_id()
    inviter_global_id = await _create_inviter(
        integration_session_factory,
        tg_id=inviter_tg_id,
        code="CORE1636",
    )

    async with (
        integration_session_factory() as session,
        session.begin(),
    ):
        result = await create_new_account(
            session,
            NewAccountRequest(
                provider=AuthProvider.TELEGRAM,
                tg_id=invitee_tg_id,
                referral_start_param="ref_CORE1636",
            ),
        )

    assert result.referral_attached is True
    assert result.referral_reason == "attached"
    async with integration_session_factory() as session:
        link = await session.scalar(
            select(ReferralLink).where(
                ReferralLink.invitee_global_id
                == result.global_id.value
            )
        )
        assert link is not None
        assert link.inviter_global_id == inviter_global_id
        assert link.invitee_global_id == result.global_id.value


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("bad code", "invalid_code"),
        ("UNKNOWN9", "code_not_found"),
    ],
)
async def test_невалидный_referral_отклоняется_до_user(
    integration_session_factory: async_sessionmaker[AsyncSession],
    next_referral_tg_id: Callable[[], int],
    raw: str,
    reason: str,
) -> None:
    tg_id = next_referral_tg_id()
    with pytest.raises(AccountRegistrationError) as captured:
        async with (
            integration_session_factory() as session,
            session.begin(),
        ):
            await create_new_account(
                session,
                NewAccountRequest(
                    provider=AuthProvider.TELEGRAM,
                    tg_id=tg_id,
                    referral_start_param=raw,
                ),
            )
    assert captured.value.reason == reason
    assert await _count_users(integration_session_factory) == 0


async def test_self_referral_отклоняется_до_account(
    integration_session_factory: async_sessionmaker[AsyncSession],
    next_referral_tg_id: Callable[[], int],
) -> None:
    inviter_tg_id = next_referral_tg_id()
    await _create_inviter(
        integration_session_factory,
        tg_id=inviter_tg_id,
        code="SELF1636",
    )

    with pytest.raises(AccountRegistrationError) as captured:
        async with (
            integration_session_factory() as session,
            session.begin(),
        ):
            await create_new_account(
                session,
                NewAccountRequest(
                    provider=AuthProvider.TELEGRAM,
                    tg_id=inviter_tg_id,
                    referral_start_param="SELF1636",
                ),
            )
    assert captured.value.reason == "self_ref"
    assert await _count_users(integration_session_factory) == 1


async def test_existing_account_не_получает_late_referral(
    integration_session_factory: async_sessionmaker[AsyncSession],
    next_referral_tg_id: Callable[[], int],
) -> None:
    inviter_tg_id = next_referral_tg_id()
    existing_tg_id = next_referral_tg_id()
    await _create_inviter(
        integration_session_factory,
        tg_id=inviter_tg_id,
        code="LATE1636",
    )
    async with (
        integration_session_factory() as session,
        session.begin(),
    ):
        existing = User()
        session.add(existing)
        await session.flush()
        session.add(
            UserIdentity(
                global_id=int(existing.global_id),
                provider="telegram",
                provider_tenant="default",
                provider_subject=str(existing_tg_id),
                status="active",
                is_primary=True,
                is_verified=True,
                verified_at=datetime.now(UTC),
            )
        )

    with pytest.raises(AccountRegistrationError) as captured:
        async with (
            integration_session_factory() as session,
            session.begin(),
        ):
            await create_new_account(
                session,
                NewAccountRequest(
                    provider=AuthProvider.TELEGRAM,
                    tg_id=existing_tg_id,
                    referral_start_param="LATE1636",
                ),
            )
    assert captured.value.reason == "ACCOUNT_ALREADY_EXISTS"
    async with integration_session_factory() as session:
        links = await session.scalar(select(func.count(ReferralLink.id)))
        assert int(links or 0) == 0


async def test_ton_only_account_создаётся_без_fake_tg_id(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with (
        integration_session_factory() as session,
        session.begin(),
    ):
        result = await create_new_account(
            session,
            NewAccountRequest(
                provider=AuthProvider.TON,
                tg_id=None,
            ),
        )

    assert result.tg_id is None
    async with integration_session_factory() as session:
        user = await session.scalar(
            select(User).where(User.global_id == result.global_id.value)
        )
        telegram_identity = await session.scalar(
            select(UserIdentity).where(
                UserIdentity.global_id == result.global_id.value,
                UserIdentity.provider == AuthProvider.TELEGRAM.value,
            )
        )
        assert user is not None
        assert telegram_identity is None


async def test_ton_referral_создаётся_по_global_id_без_fake_tg_id(
    integration_session_factory: async_sessionmaker[AsyncSession],
    next_referral_tg_id: Callable[[], int],
) -> None:
    inviter_tg_id = next_referral_tg_id()
    inviter_global_id = await _create_inviter(
        integration_session_factory,
        tg_id=inviter_tg_id,
        code="TON1639A",
    )

    async with (
        integration_session_factory() as session,
        session.begin(),
    ):
        result = await create_new_account(
            session,
            NewAccountRequest(
                provider=AuthProvider.TON,
                tg_id=None,
                referral_start_param="TON1639A",
            ),
        )

    assert result.referral_attached is True
    assert result.tg_id is None
    async with integration_session_factory() as session:
        link = await session.scalar(
            select(ReferralLink).where(
                ReferralLink.invitee_global_id == result.global_id.value
            )
        )
    assert link is not None
    assert link.inviter_global_id == inviter_global_id


async def test_открытая_транзакция_обязательна(
    integration_session_factory: async_sessionmaker[AsyncSession],
    next_referral_tg_id: Callable[[], int],
) -> None:
    async with integration_session_factory() as session:
        with pytest.raises(AccountRegistrationError) as captured:
            await create_new_account(
                session,
                NewAccountRequest(
                    provider=AuthProvider.TELEGRAM,
                    tg_id=next_referral_tg_id(),
                ),
            )
    assert captured.value.reason == "TRANSACTION_REQUIRED"
