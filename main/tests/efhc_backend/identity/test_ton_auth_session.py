"""Узкие contracts TON session/logout цикла 1618."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest
from app.identity.auth_context import AuthContext
from app.identity.auth_provider import AuthProvider
from app.identity.auth_runtime_services import (
    AuthSessionService,
    IssuedAuthSession,
)
from app.identity.provider_registry import (
    finalize_verified_provider_subject,
)
from app.identity.ton_account_registration import (
    TonAccountRegistration,
)
from app.identity.ton_auth_session import (
    TonAuthSessionResult,
    build_ton_auth_session_contract,
)
from app.identity.types import GlobalId
from app.routes.auth_session_routes import (
    get_current_auth_session,
    logout_auth_session,
)
from fastapi import HTTPException, Response


def _context() -> AuthContext:
    identity = finalize_verified_provider_subject(
        AuthProvider.TON,
        "0:" + "a" * 64,
    )
    return AuthContext(
        global_id=GlobalId(42),
        verified_identity=identity,
        roles=frozenset({"user"}),
        session_id="00000000-0000-0000-0000-000000000042",
    )


def test_ton_auth_session_contract_фиксирует_границы() -> None:
    contract = build_ton_auth_session_contract()
    assert contract["цикл"] == 1618
    assert contract["session"]["raw_token_stored"] is False
    assert contract["session"]["logout_revokes"] is True
    assert contract["frontend_transport"]["storage"] == "sessionStorage"
    assert contract["запреты"]["cycle_1619_adapter"] is True


def test_ton_auth_result_скрывает_session_token_в_repr() -> None:
    token = "S" * 43
    result = TonAuthSessionResult(
        account=TonAccountRegistration(
            global_id=GlobalId(42),
            outcome="existing_identity",
            identity_id=1,
            binding_id=2,
        ),
        session=IssuedAuthSession(
            UUID(int=3),
            token,
            datetime.now(UTC),
        ),
    )
    assert token not in repr(result)
    assert "<redacted>" in repr(result)


@pytest.mark.asyncio
async def test_current_session_response_не_раскрывает_subject_и_token() -> None:
    response = Response()
    result = await get_current_auth_session(response, _context())
    payload = result.model_dump(mode="json")
    assert payload == {
        "global_id": "0000000042",
        "provider": "ton",
        "roles": ["user"],
    }
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.asyncio
async def test_logout_отзывает_session_и_возвращает_204() -> None:
    class Service:
        async def revoke(self, token: object) -> bool:
            return token == "S" * 43

    response = await logout_auth_session(
        "S" * 43,
        cast(AuthSessionService, Service()),
    )
    assert response.status_code == 204
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.asyncio
async def test_logout_invalid_session_возвращает_401() -> None:
    class Service:
        async def revoke(self, _token: object) -> bool:
            return False

    with pytest.raises(HTTPException) as captured:
        await logout_auth_session(
            "S" * 43,
            cast(AuthSessionService, Service()),
        )
    assert captured.value.status_code == 401
