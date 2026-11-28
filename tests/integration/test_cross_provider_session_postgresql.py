"""Real PostgreSQL/API proof cross-provider session closure цикла 1630."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

import pytest
from app.deps import get_db
from app.identity.auth_dependencies import get_auth_session_service
from app.identity.auth_provider import AuthProvider
from app.identity.auth_runtime_services import AuthSessionService
from app.identity.types import GlobalId, format_global_id
from app.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.usefixtures("db_clean"),
]

TELEGRAM_SUBJECT = "8900001630"
TON_SUBJECT = "0:" + "16" * 32


async def _seed_cross_provider_account(
    db: AsyncSession,
) -> tuple[GlobalId, int, int]:
    global_id = int(
        (
            await db.execute(
                text(
                    "INSERT INTO efhc_core.users (username) "
                    "VALUES ('cross-provider-session') RETURNING global_id"
                ),
            )
        ).scalar_one()
    )
    telegram_identity = int(
        (
            await db.execute(
                text(
                    """
                    INSERT INTO efhc_core.user_identities (
                        global_id, provider, provider_tenant,
                        provider_subject, status, is_primary,
                        is_verified, verified_at
                    ) VALUES (
                        :global_id, 'telegram', 'default', :subject,
                        'active', TRUE, TRUE, now()
                    ) RETURNING id
                    """
                ),
                {
                    "global_id": global_id,
                    "subject": TELEGRAM_SUBJECT,
                },
            )
        ).scalar_one()
    )
    ton_identity = int(
        (
            await db.execute(
                text(
                    """
                    INSERT INTO efhc_core.user_identities (
                        global_id, provider, provider_tenant,
                        provider_subject, status, is_primary,
                        is_verified, verified_at
                    ) VALUES (
                        :global_id, 'ton', 'default', :subject,
                        'active', FALSE, TRUE, now()
                    ) RETURNING id
                    """
                ),
                {
                    "global_id": global_id,
                    "subject": TON_SUBJECT,
                },
            )
        ).scalar_one()
    )
    await db.commit()
    return GlobalId.from_database(global_id), telegram_identity, ton_identity


@asynccontextmanager
async def _client(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    def override_service() -> AuthSessionService:
        return AuthSessionService(factory)

    async def override_db() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_auth_session_service] = override_service
    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


async def test_telegram_и_ton_sessions_видят_один_global_id(
    db_session: AsyncSession,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    global_id, telegram_identity, ton_identity = (
        await _seed_cross_provider_account(db_session)
    )
    sessions = AuthSessionService(integration_session_factory)
    telegram_session = await sessions.issue(
        global_id=global_id,
        identity_id=telegram_identity,
        ttl=timedelta(hours=1),
    )
    ton_session = await sessions.issue(
        global_id=global_id,
        identity_id=ton_identity,
        ttl=timedelta(hours=1),
    )

    async with _client(integration_session_factory) as client:
        telegram_response = await client.get(
            "/api/auth/session",
            headers={
                "Authorization": f"Bearer {telegram_session.token}",
            },
        )
        ton_response = await client.get(
            "/api/auth/session",
            headers={"Authorization": f"Bearer {ton_session.token}"},
        )

    assert telegram_response.status_code == 200
    assert ton_response.status_code == 200
    telegram_payload = telegram_response.json()
    ton_payload = ton_response.json()
    expected = str(format_global_id(global_id))
    assert telegram_payload["global_id"] == expected
    assert ton_payload["global_id"] == expected
    assert telegram_payload["provider"] == AuthProvider.TELEGRAM.value
    assert ton_payload["provider"] == AuthProvider.TON.value


async def test_business_api_raw_init_data_fallback_закрыт(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client(integration_session_factory) as client:
        response = await client.post(
            "/api/sync/me?fresh=0",
            headers={"X-Telegram-Init-Data": "query_id=legacy-fallback"},
        )
    assert response.status_code == 401
    payload = response.json()
    assert payload.get("error") == "http_error"
    assert payload.get("message") == "Требуется аутентификация"
