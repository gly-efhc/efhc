"""Real PostgreSQL Telegram adapter/session tests цикла 1619."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime

import pytest
from app.identity.auth_provider import AuthProvider
from app.identity.telegram_auth_session import (
    TelegramAuthSessionError,
    TelegramAuthSessionService,
)
from app.identity.telegram_init_data import TelegramInitDataAdapter
from app.identity.user_identities_storage_contract import (
    UserIdentityStatus,
)
from app.models.auth_models import AuthSession
from app.models.external_events_models import ProcessedExternalEvent
from app.models.identity_models import UserIdentity
from app.models.user_models import User
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("db_clean")]
NOW = datetime(2026, 7, 31, 0, 0, tzinfo=UTC)


def _verified(tg_id: int, label: str):
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


@pytest.mark.asyncio
async def test_existing_identity_возвращает_тот_же_account(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with integration_session_factory() as session, session.begin():
        user = User()
        session.add(user)
        await session.flush()
        identity = UserIdentity(
            global_id=int(user.global_id),
            provider=AuthProvider.TELEGRAM.value,
            provider_subject="7001",
            status=UserIdentityStatus.ACTIVE.value,
            is_primary=True,
            is_verified=True,
            verified_at=NOW,
        )
        session.add(identity)
        await session.flush()
        expected = int(user.global_id)

    result = await TelegramAuthSessionService(
        integration_session_factory
    ).login(_verified(7001, "existing-identity"))
    assert result.account.global_id.value == expected
    assert result.account.outcome == "existing_identity"


@pytest.mark.asyncio
async def test_account_без_identity_не_используется_как_telegram_fallback(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with integration_session_factory() as session, session.begin():
        user = User()
        session.add(user)
        await session.flush()
        existing_global_id = int(user.global_id)

    result = await TelegramAuthSessionService(
        integration_session_factory
    ).login(_verified(7002, "no-identity-account"))
    assert result.account.outcome == "registered"
    assert result.account.global_id.value != existing_global_id

    async with integration_session_factory() as session:
        users = await session.scalar(select(func.count(User.global_id)))
        identities = await session.scalar(
            select(func.count(UserIdentity.id)).where(
                UserIdentity.provider == "telegram",
                UserIdentity.provider_subject == "7002",
            )
        )
    assert int(users or 0) == 2
    assert int(identities or 0) == 1


@pytest.mark.asyncio
async def test_new_telegram_login_создаёт_account_identity_session(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    result = await TelegramAuthSessionService(
        integration_session_factory
    ).login(_verified(7003, "new-account"))
    assert result.account.outcome == "registered"

    async with integration_session_factory() as session:
        user = await session.scalar(
            select(User).where(
                User.global_id == result.account.global_id.value
            )
        )
        sessions = await session.scalar(
            select(func.count(AuthSession.id)).where(
                AuthSession.global_id
                == result.account.global_id.value
            )
        )
    assert user is not None
    assert int(user.global_id) == result.account.global_id.value
    assert int(sessions or 0) == 1


@pytest.mark.asyncio
async def test_repeat_login_открывает_тот_же_account_новой_session(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TelegramAuthSessionService(integration_session_factory)
    first = await service.login(_verified(7004, "repeat-one"))
    second = await service.login(_verified(7004, "repeat-two"))
    assert first.account.global_id == second.account.global_id
    assert first.session.token != second.session.token


@pytest.mark.asyncio
async def test_exact_init_data_replay_отклоняется(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TelegramAuthSessionService(integration_session_factory)
    verified = _verified(7005, "replay")
    await service.login(verified)
    with pytest.raises(TelegramAuthSessionError) as captured:
        await service.login(verified)
    assert captured.value.reason == "INIT_DATA_REPLAY"


@pytest.mark.asyncio
async def test_concurrent_first_login_создаёт_один_account(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TelegramAuthSessionService(integration_session_factory)
    results = await asyncio.gather(
        *(
            service.login(_verified(7006, f"concurrent-{index}"))
            for index in range(6)
        )
    )
    global_ids = {item.account.global_id.value for item in results}
    assert len(global_ids) == 1
    assert len({item.session.token for item in results}) == 6

    async with integration_session_factory() as session:
        users = await session.scalar(
            select(func.count(User.global_id)).where(
                User.global_id.in_(global_ids)
            )
        )
        identities = await session.scalar(
            select(func.count(UserIdentity.id)).where(
                UserIdentity.provider_subject == "7006"
            )
        )
        replay_rows = await session.scalar(
            select(func.count(ProcessedExternalEvent.id)).where(
                ProcessedExternalEvent.provider
                == "telegram_init_data_auth"
            )
        )
    assert int(users or 0) == 1
    assert int(identities or 0) == 1
    assert int(replay_rows or 0) == 6
