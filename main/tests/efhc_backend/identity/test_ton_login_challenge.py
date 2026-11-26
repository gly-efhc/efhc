from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from app.identity.auth_provider import AuthProvider
from app.identity.auth_runtime_services import IssuedAuthChallenge
from app.identity.ton_login_challenge import (
    TON_LOGIN_CHALLENGE_TTL,
    TON_LOGIN_PURPOSE,
    TonLoginChallengeService,
    TonLoginDomainError,
    canonicalize_ton_login_domain,
    resolve_ton_login_domain,
)


class FakeChallengeIssuer:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}

    async def issue(self, **kwargs: object) -> IssuedAuthChallenge:
        self.kwargs = kwargs
        return IssuedAuthChallenge(
            challenge_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
            token="A" * 43,
            expires_at=datetime(2026, 7, 30, 20, 10, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_ton_login_challenge_использует_auth_storage_без_telegram() -> None:
    issuer = FakeChallengeIssuer()
    service = TonLoginChallengeService(issuer)
    result = await service.issue(domain="APP.Example.org")

    assert issuer.kwargs == {
        "provider": AuthProvider.TON,
        "purpose": TON_LOGIN_PURPOSE,
        "domain": "app.example.org",
        "ttl": TON_LOGIN_CHALLENGE_TTL,
    }
    assert result.provider == "ton"
    assert result.purpose == TON_LOGIN_PURPOSE
    assert result.payload == "A" * 43
    assert "payload='<redacted>'" in repr(result)
    assert "tg_id" not in issuer.kwargs


def test_configured_public_url_преобразуется_только_в_hostname() -> None:
    assert canonicalize_ton_login_domain(
        "https://App.Example.org/"
    ) == "app.example.org"


def test_local_domain_может_использовать_request_hostname() -> None:
    assert resolve_ton_login_domain(
        environment="local",
        app_url="",
        frontend_url="",
        request_hostname="localhost",
    ) == "localhost"


def test_production_требует_configured_domain() -> None:
    with pytest.raises(
        TonLoginDomainError,
        match="Domain TON login недействителен",
    ) as error:
        resolve_ton_login_domain(
            environment="prod",
            app_url="",
            frontend_url="",
            request_hostname="attacker.example",
        )
    assert error.value.reason == "CONFIGURED_DOMAIN_REQUIRED"


@pytest.mark.parametrize(
    "value",
    [
        "https://user:pass@example.org",
        "https://example.org/path",
        "https://example.org?query=1",
        "https://example.org#fragment",
        " example.org",
        "example.org ",
        "",
        None,
    ],
)
def test_неоднозначные_domains_fail_closed(value: object) -> None:
    with pytest.raises(TonLoginDomainError):
        canonicalize_ton_login_domain(value)
