"""Cross-provider PostgreSQL qualification единого центра цикла 1639."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.identity.auth_errors import InvalidAuthRuntimeInput
from app.identity.auth_provider import AuthProvider
from app.identity.provider_registry import (
    finalize_verified_provider_subject,
)
from app.identity.telegram_auth_session import (
    TelegramAuthSessionError,
    TelegramAuthSessionService,
)
from app.identity.telegram_init_data import TelegramInitDataAdapter
from app.identity.ton_auth_session import (
    TonAuthSessionError,
    TonAuthSessionService,
)
from app.identity.ton_proof_verification import VerifiedTonProof
from app.models.identity_models import UserIdentity
from app.models.referral_codes_models import ReferralCode
from app.models.referral_models import ReferralLink
from app.models.user_models import User
from app.models.wallets_models import WalletBinding
from app.services.referral_service import onboard_user_at_first_creation
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.usefixtures("db_clean"),
]
NOW = datetime(2026, 8, 3, 0, 0, tzinfo=UTC)


def _telegram_verified(tg_id: int, label: str):
    digest = hashlib.sha256(label.encode("ascii")).hexdigest()
    adapter = TelegramInitDataAdapter(
        lambda _raw: {
            "auth_date": str(int(NOW.timestamp())),
            "hash": digest,
            "user": {"id": tg_id},
        },
        clock=lambda: NOW,
    )
    return adapter.verify(f"label={label}&hash={digest}")


def _ton_proof(label: str) -> VerifiedTonProof:
    digest = hashlib.sha256(
        f"{label}:{uuid4()}".encode("ascii")
    ).hexdigest()
    subject = f"0:{digest}"
    return VerifiedTonProof(
        challenge_id=uuid4(),
        verified_identity=finalize_verified_provider_subject(
            AuthProvider.TON,
            subject,
        ),
        network="mainnet",
        verified_at=NOW,
        key_source="registration_equivalence_fixture",
    )


async def _create_owner_and_code(
    factory: async_sessionmaker[AsyncSession],
    *,
    tg_id: int,
    code: str,
) -> int:
    async with factory() as session, session.begin():
        user = User()
        session.add(user)
        await session.flush()
        global_id = int(user.global_id)
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


async def test_bot_webapp_ton_дают_одинаковую_canonical_attribution(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    inviter_tg_id = 8_982_000_001
    inviter_global_id = await _create_owner_and_code(
        integration_session_factory,
        tg_id=inviter_tg_id,
        code="ALL1639A",
    )

    bot_tg_id = 8_982_000_002
    async with integration_session_factory() as session:
        bot = await onboard_user_at_first_creation(
            session,
            tg_id=bot_tg_id,
            start_param="ALL1639A",
        )
    assert bot.created is True
    assert bot.referral_attached is True

    web_tg_id = 8_982_000_003
    web = await TelegramAuthSessionService(
        integration_session_factory
    ).login(
        _telegram_verified(web_tg_id, "web-equivalence"),
        referral_start_param="ALL1639A",
    )
    ton = await TonAuthSessionService(
        integration_session_factory
    ).login(
        _ton_proof("ton-equivalence"),
        referral_start_param="ALL1639A",
    )

    async with integration_session_factory() as session:
        bot_global_id = await session.scalar(
            select(UserIdentity.global_id).where(
                UserIdentity.provider == AuthProvider.TELEGRAM.value,
                UserIdentity.provider_subject == str(bot_tg_id),
            )
        )
        links = list(
            (
                await session.scalars(
                    select(ReferralLink).where(
                        ReferralLink.inviter_global_id
                        == inviter_global_id
                    )
                )
            ).all()
        )
    assert len(links) == 3
    assert {link.inviter_global_id for link in links} == {inviter_global_id}
    assert bot_global_id is not None
    assert {link.invitee_global_id for link in links} == {
        int(bot_global_id),
        web.account.global_id.value,
        ton.account.global_id.value,
    }
    assert sum(
        link.invitee_global_id == ton.account.global_id.value
        for link in links
    ) == 1


async def test_legacy_bot_user_webapp_login_не_создаёт_дубликат(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tg_id = 8_982_000_010
    async with integration_session_factory() as session:
        result = await onboard_user_at_first_creation(
            session,
            tg_id=tg_id,
        )
    assert result.created is True

    login = await TelegramAuthSessionService(
        integration_session_factory
    ).login(_telegram_verified(tg_id, "legacy-webapp"))
    assert login.account.outcome in {
        "existing_identity",
        "existing_legacy_account",
    }

    async with integration_session_factory() as session:
        users = await session.scalar(
            select(func.count(User.global_id))
            .join(UserIdentity, UserIdentity.global_id == User.global_id)
            .where(
                UserIdentity.provider == AuthProvider.TELEGRAM.value,
                UserIdentity.provider_subject == str(tg_id),
            )
        )
        identities = await session.scalar(
            select(func.count(UserIdentity.id)).where(
                UserIdentity.provider == AuthProvider.TELEGRAM.value,
                UserIdentity.provider_subject == str(tg_id),
            )
        )
    assert int(users or 0) == 1
    assert int(identities or 0) == 1


async def test_межпровайдерный_cycle_не_создаётся_late_binding(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    a_tg_id = 8_982_000_020
    a_global_id = await _create_owner_and_code(
        integration_session_factory,
        tg_id=a_tg_id,
        code="A1639CYCLE",
    )
    b = await TonAuthSessionService(
        integration_session_factory
    ).login(
        _ton_proof("cycle-b"),
        referral_start_param="A1639CYCLE",
    )

    async with integration_session_factory() as session, session.begin():
        session.add(
            ReferralCode(
                code="B1639CYCLE",
                inviter_global_id=b.account.global_id.value,
            )
        )

    existing = await TelegramAuthSessionService(
        integration_session_factory
    ).login(
        _telegram_verified(a_tg_id, "cycle-a-existing"),
        referral_start_param="B1639CYCLE",
    )
    assert existing.account.outcome == "existing_identity"
    assert existing.account.global_id.value == a_global_id

    async with integration_session_factory() as session:
        links = list((await session.scalars(select(ReferralLink))).all())
    assert len(links) == 1
    assert links[0].inviter_global_id == a_global_id
    assert links[0].invitee_global_id == b.account.global_id.value


async def test_telegram_session_failure_откатывает_account_referral_identity(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _create_owner_and_code(
        integration_session_factory,
        tg_id=8_982_000_030,
        code="ROLL1639T",
    )
    tg_id = 8_982_000_031
    service = TelegramAuthSessionService(integration_session_factory)

    async def fail_issue(*_args, **_kwargs):
        raise InvalidAuthRuntimeInput()

    service._session_service.issue_in_transaction = fail_issue  # type: ignore[method-assign]
    with pytest.raises(TelegramAuthSessionError) as captured:
        await service.login(
            _telegram_verified(tg_id, "rollback-telegram"),
            referral_start_param="ROLL1639T",
        )
    assert captured.value.reason == "SESSION_ISSUE_DENIED"

    async with integration_session_factory() as session:
        users = await session.scalar(
            select(func.count(User.global_id))
            .join(UserIdentity, UserIdentity.global_id == User.global_id)
            .where(
                UserIdentity.provider == AuthProvider.TELEGRAM.value,
                UserIdentity.provider_subject == str(tg_id),
            )
        )
        identities = await session.scalar(
            select(func.count(UserIdentity.id)).where(
                UserIdentity.provider_subject == str(tg_id)
            )
        )
        links = await session.scalar(
            select(func.count(ReferralLink.id))
        )
    assert int(users or 0) == 0
    assert int(identities or 0) == 0
    assert int(links or 0) == 0


async def test_ton_session_failure_откатывает_account_referral_identity(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _create_owner_and_code(
        integration_session_factory,
        tg_id=8_982_000_040,
        code="ROLL1639N",
    )
    proof = _ton_proof("rollback-ton")
    service = TonAuthSessionService(integration_session_factory)

    async def fail_issue(*_args, **_kwargs):
        raise InvalidAuthRuntimeInput()

    service._session_service.issue_in_transaction = fail_issue  # type: ignore[method-assign]
    with pytest.raises(TonAuthSessionError) as captured:
        await service.login(
            proof,
            referral_start_param="ROLL1639N",
        )
    assert captured.value.reason == "SESSION_ISSUE_DENIED"

    subject = proof.ton_wallet_id
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
        links = await session.scalar(
            select(func.count(ReferralLink.id))
        )
    assert int(identities or 0) == 0
    assert int(bindings or 0) == 0
    assert int(links or 0) == 0
