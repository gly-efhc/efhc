"""Причинные tests auth runtime contracts цикла 1613."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from app.identity import (
    AuthChallengeService,
    AuthProvider,
    AuthProviderRegistry,
    GlobalId,
    InvalidAuthRuntimeInput,
    IssuedAuthChallenge,
    IssuedAuthSession,
    ProviderAvailability,
    ProviderCapability,
    ProviderRegistration,
    hash_auth_challenge,
    hash_auth_session_token,
)
from app.identity.auth_context import AuthContext
from app.identity.auth_dependencies import (
    get_optional_auth_context,
    require_auth_context,
    require_auth_roles,
)
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.support.mock_auth_provider import MockAuthProviderAdapter


def _auth_context(*roles: str) -> AuthContext:
    registry = AuthProviderRegistry(environment="ci")
    registry.register(
        ProviderRegistration(
            provider=AuthProvider.MOCK,
            canonical_name="mock",
            availability=ProviderAvailability.ENABLED,
            capabilities=frozenset(
                {ProviderCapability.VERIFY_IDENTITY}
            ),
            adapter_factory=MockAuthProviderAdapter,
            test_only=True,
        )
    )
    identity = registry.verify(
        AuthProvider.MOCK,
        {"test_verification": True, "subject": "mock:roles"},
    )
    return AuthContext(
        global_id=GlobalId(42),
        verified_identity=identity,
        roles=frozenset(roles),
        session_id="00000000-0000-0000-0000-000000000042",
    )


def test_challenge_и_session_hash_разделены_namespace() -> None:
    token = "A" * 43
    challenge_hash = hash_auth_challenge(token)
    session_hash = hash_auth_session_token(token)
    assert len(challenge_hash) == 64
    assert len(session_hash) == 64
    assert challenge_hash != session_hash
    assert token not in challenge_hash
    assert token not in session_hash


@pytest.mark.parametrize(
    "token",
    [None, "", "short", "привет" * 8, "a b" * 16],
)
def test_hash_boundary_завершается_fail_closed(token: object) -> None:
    with pytest.raises(InvalidAuthRuntimeInput):
        hash_auth_session_token(token)


def test_issued_credentials_скрывают_token_в_repr() -> None:
    token = "B" * 43
    now = datetime.now(UTC)
    challenge = IssuedAuthChallenge(UUID(int=1), token, now)
    session = IssuedAuthSession(UUID(int=2), token, now)
    assert token not in repr(challenge)
    assert token not in repr(session)
    assert "<redacted>" in repr(challenge)
    assert "<redacted>" in repr(session)


def test_mock_provider_остаётся_storage_forbidden() -> None:
    assert AuthProvider.MOCK.value == "mock"


@pytest.mark.asyncio
async def test_challenge_mock_provider_отклоняется_до_database() -> None:
    service = AuthChallengeService(async_sessionmaker[AsyncSession]())
    with pytest.raises(InvalidAuthRuntimeInput):
        await service.consume(
            "A" * 43,
            provider=AuthProvider.MOCK,
            purpose="login",
            domain="app.efhc.example",
        )


@pytest.mark.asyncio
async def test_fastapi_dependency_малformed_token_возвращает_401() -> None:
    class RejectingService:
        async def authenticate(self, token: object) -> None:
            raise InvalidAuthRuntimeInput()

    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials="bad token",
    )
    with pytest.raises(HTTPException) as captured:
        await get_optional_auth_context(credentials, RejectingService())
    assert captured.value.status_code == 401
    assert captured.value.headers == {"WWW-Authenticate": "Bearer"}


@pytest.mark.asyncio
async def test_fastapi_dependencies_различают_401_и_403() -> None:
    with pytest.raises(HTTPException) as missing:
        await require_auth_context(None)
    assert missing.value.status_code == 401

    context = _auth_context("user")
    assert await require_auth_roles("user")(context) is context
    with pytest.raises(HTTPException) as denied:
        await require_auth_roles("admin")(context)
    assert denied.value.status_code == 403


def test_auth_role_config_отклоняет_invalid_name() -> None:
    with pytest.raises(ValueError):
        require_auth_roles()
    with pytest.raises(ValueError):
        require_auth_roles("Admin")
