"""PostgreSQL-доказательства Bot migration цикла 1637."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from app.models.identity_models import UserIdentity
from app.models.referral_codes_models import ReferralCode
from app.models.referral_models import ReferralLink
from app.models.user_models import User
from app.services import referral_service
from app.services.referral_service import onboard_user_at_first_creation
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.usefixtures("db_clean"),
]


async def _создать_пригласившего(
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


async def test_bot_создаёт_user_referral_и_identity_атомарно(
    integration_session_factory: async_sessionmaker[AsyncSession],
    next_referral_tg_id: Callable[[], int],
) -> None:
    inviter_tg_id = next_referral_tg_id()
    invitee_tg_id = next_referral_tg_id()
    inviter_global_id = await _создать_пригласившего(
        integration_session_factory,
        tg_id=inviter_tg_id,
        code="BOT1637A",
    )

    async with integration_session_factory() as session:
        result = await onboard_user_at_first_creation(
            session,
            tg_id=invitee_tg_id,
            username="bot_invitee",
            start_param="ref_BOT1637A",
        )

    assert result.created is True
    assert result.referral_attached is True
    assert result.inviter_global_id == inviter_global_id

    async with integration_session_factory() as session:
        user = await session.scalar(
            select(User)
            .join(UserIdentity, UserIdentity.global_id == User.global_id)
            .where(UserIdentity.provider_subject == str(invitee_tg_id))
        )
        identity = await session.scalar(
            select(UserIdentity).where(
                UserIdentity.provider == "telegram",
                UserIdentity.provider_subject == str(invitee_tg_id),
            )
        )
        assert user is not None
        assert user.global_id is not None
        link = await session.scalar(
            select(ReferralLink).where(
                ReferralLink.invitee_global_id == int(user.global_id)
            )
        )

    assert user is not None
    assert user.global_id is not None
    assert identity is not None
    assert identity.global_id == int(user.global_id)
    assert identity.is_verified is True
    assert identity.is_primary is True
    assert link is not None
    assert link.inviter_global_id == inviter_global_id
    assert link.invitee_global_id == int(user.global_id)


async def test_identity_failure_откатывает_user_и_referral(
    integration_session_factory: async_sessionmaker[AsyncSession],
    next_referral_tg_id: Callable[[], int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inviter_tg_id = next_referral_tg_id()
    invitee_tg_id = next_referral_tg_id()
    await _создать_пригласившего(
        integration_session_factory,
        tg_id=inviter_tg_id,
        code="BOT1637B",
    )

    async def _ошибка_identity(*args: object, **kwargs: object) -> None:
        _ = args, kwargs
        raise RuntimeError("forced identity failure")

    monkeypatch.setattr(
        referral_service,
        "_create_bot_user_identity",
        _ошибка_identity,
    )
    with pytest.raises(RuntimeError, match="forced identity failure"):
        async with integration_session_factory() as session:
            await onboard_user_at_first_creation(
                session,
                tg_id=invitee_tg_id,
                start_param="ref_BOT1637B",
            )

    async with integration_session_factory() as session:
        users = await session.scalar(
            select(func.count(User.global_id))
            .join(UserIdentity, UserIdentity.global_id == User.global_id)
            .where(UserIdentity.provider_subject == str(invitee_tg_id))
        )
        links = await session.scalar(select(func.count(ReferralLink.id)))
        identities = await session.scalar(
            select(func.count(UserIdentity.id)).where(
                UserIdentity.provider_subject == str(invitee_tg_id)
            )
        )

    assert int(users or 0) == 0
    assert int(links or 0) == 0
    assert int(identities or 0) == 0


async def test_existing_bot_user_не_получает_late_referral(
    integration_session_factory: async_sessionmaker[AsyncSession],
    next_referral_tg_id: Callable[[], int],
) -> None:
    inviter_tg_id = next_referral_tg_id()
    existing_tg_id = next_referral_tg_id()
    await _создать_пригласившего(
        integration_session_factory,
        tg_id=inviter_tg_id,
        code="BOT1637C",
    )
    async with integration_session_factory() as session, session.begin():
        existing = User()
        session.add(existing)
        await session.flush()
        assert existing.global_id is not None
        existing_global_id = int(existing.global_id)
        session.add(
            UserIdentity(
                global_id=existing_global_id,
                provider="telegram",
                provider_tenant="default",
                provider_subject=str(existing_tg_id),
                status="active",
                is_primary=True,
                is_verified=True,
                verified_at=datetime.now(UTC),
            )
        )

    async with integration_session_factory() as session:
        result = await onboard_user_at_first_creation(
            session,
            tg_id=existing_tg_id,
            start_param="ref_BOT1637C",
        )

    assert result.created is False
    assert result.reason == "existing_user_locked"
    async with integration_session_factory() as session:
        links = await session.scalar(
            select(func.count(ReferralLink.id)).where(
                ReferralLink.invitee_global_id == existing_global_id
            )
        )
    assert int(links or 0) == 0
