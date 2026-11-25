"""Причинные tests AuthContext/resolver/redaction цикла 1610."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import fields
from types import SimpleNamespace

import pytest
from app.core.logging_core import RedactingFilter
from app.identity import (
    AUTH_PROVIDER_ERROR_CODES,
    AUTH_REDACTION_MASK,
    AuthContext,
    AuthContextResponse,
    AuthProvider,
    AuthProviderRegistry,
    GlobalId,
    IdentityResolution,
    IdentityResolutionStatus,
    IdentityResolver,
    InvalidAuthContext,
    InvalidIdentityResolution,
    ProviderAvailability,
    ProviderCapability,
    ProviderRegistration,
    VerifiedIdentity,
    build_auth_context_contract,
    build_auth_diagnostic,
    redact_auth_diagnostic,
)
from pydantic import ValidationError
from tests.support.mock_auth_provider import MockAuthProviderAdapter
from tests.support.mock_identity_resolver import MockIdentityResolver


def _registry() -> AuthProviderRegistry:
    registry = AuthProviderRegistry(environment="ci")
    registry.register(
        ProviderRegistration(
            provider=AuthProvider.MOCK,
            canonical_name=AuthProvider.MOCK.value,
            availability=ProviderAvailability.ENABLED,
            capabilities=frozenset(
                {ProviderCapability.VERIFY_IDENTITY}
            ),
            adapter_factory=MockAuthProviderAdapter,
            test_only=True,
        )
    )
    return registry


def _identity(subject: str = "Case:SENSITIVE/01") -> VerifiedIdentity:
    return _registry().verify(
        AuthProvider.MOCK,
        {
            "test_verification": True,
            "subject": subject,
        },
    )


def _context(
    *,
    subject: str = "Case:SENSITIVE/01",
    session_id: str | None = "session_ref_1234567890",
) -> AuthContext:
    return AuthContext(
        global_id=GlobalId(42),
        verified_identity=_identity(subject),
        roles=frozenset({"user", "admin.read"}),
        session_id=session_id,
    )


def test_auth_context_создаётся_только_из_nominal_identity() -> None:
    context = _context()
    assert context.global_id == GlobalId(42)
    assert context.provider is AuthProvider.MOCK
    assert context.provider_subject == "Case:SENSITIVE/01"

    with pytest.raises(InvalidAuthContext):
        AuthContext(  # type: ignore[arg-type]
            global_id=42,
            verified_identity=_identity(),
        )
    with pytest.raises(InvalidAuthContext):
        AuthContext(  # type: ignore[arg-type]
            global_id=GlobalId(42),
            verified_identity={"provider": "mock"},
        )


def test_auth_context_не_содержит_provider_owner_fields() -> None:
    names = {field.name for field in fields(AuthContext)}
    assert names == {
        "global_id",
        "provider",
        "provider_subject",
        "roles",
        "session_id",
    }
    assert "tg_id" not in names
    assert "wallet_address" not in names
    assert "user" not in names
    assert "identity_id" not in names


def test_endpoint_contract_не_зависит_от_tg_id() -> None:
    response = AuthContextResponse.from_auth_context(_context())
    payload = response.model_dump(mode="json")
    assert payload == {
        "global_id": "0000000042",
        "provider": "mock",
        "roles": ["admin.read", "user"],
    }
    assert "tg_id" not in payload
    assert "provider_subject" not in payload
    assert "session_id" not in payload

    schema = AuthContextResponse.model_json_schema(mode="serialization")
    properties = schema["properties"]
    assert set(properties) == {"global_id", "provider", "roles"}


def test_endpoint_contract_запрещает_лишние_provider_data() -> None:
    with pytest.raises(ValidationError):
        AuthContextResponse(
            global_id=GlobalId(42),
            provider=AuthProvider.MOCK,
            roles=("user",),
            tg_id=42,  # type: ignore[call-arg]
        )


def test_roles_и_session_reference_проверяются_строго() -> None:
    with pytest.raises(InvalidAuthContext):
        AuthContext(
            global_id=GlobalId(42),
            verified_identity=_identity(),
            roles={"user"},  # type: ignore[arg-type]
        )
    with pytest.raises(InvalidAuthContext):
        AuthContext(
            global_id=GlobalId(42),
            verified_identity=_identity(),
            roles=frozenset({"Пользователь"}),
        )
    with pytest.raises(InvalidAuthContext):
        AuthContext(
            global_id=GlobalId(42),
            verified_identity=_identity(),
            session_id="short",
        )


def test_auth_context_repr_не_раскрывает_subject_и_session() -> None:
    secret_subject = "VERY_SECRET_PROVIDER_SUBJECT"
    secret_session = "session_ref_VERY_SECRET_12345"
    rendered = repr(
        _context(
            subject=secret_subject,
            session_id=secret_session,
        )
    )
    assert secret_subject not in rendered
    assert secret_session not in rendered
    assert rendered.count("<redacted>") == 2


def test_identity_resolution_имеет_fail_closed_outcomes() -> None:
    resolved = IdentityResolution.resolved(GlobalId(42))
    missing = IdentityResolution.not_found()
    conflict = IdentityResolution.conflict()

    assert resolved.status is IdentityResolutionStatus.RESOLVED
    assert resolved.global_id == GlobalId(42)
    assert missing.status is IdentityResolutionStatus.NOT_FOUND
    assert missing.global_id is None
    assert conflict.status is IdentityResolutionStatus.CONFLICT
    assert conflict.global_id is None


def test_identity_resolution_нельзя_собрать_вручную() -> None:
    with pytest.raises(InvalidIdentityResolution):
        IdentityResolution(
            status=IdentityResolutionStatus.RESOLVED,
            global_id=GlobalId(42),
        )
    with pytest.raises(InvalidIdentityResolution):
        IdentityResolution.resolved(42)  # type: ignore[arg-type]


def test_тестовый_resolver_принимает_только_verified_identity() -> None:
    resolution = IdentityResolution.resolved(GlobalId(42))
    resolver = MockIdentityResolver(resolution)
    assert isinstance(resolver, IdentityResolver)

    identity = _identity()
    result = asyncio.run(
        resolver.resolve_verified_identity(identity)
    )
    assert result is resolution
    assert resolver.received == [identity]

    with pytest.raises(TypeError):
        asyncio.run(
            resolver.resolve_verified_identity(
                # type: ignore[arg-type]
                {"provider": "mock", "subject": "raw"}
            )
        )


def test_auth_diagnostics_редактируют_nested_secrets() -> None:
    secret_subject = "SECRET_PROVIDER_SUBJECT"
    secret_session = "session_ref_SECRET_123456789"
    context = _context(
        subject=secret_subject,
        session_id=secret_session,
    )
    diagnostic = build_auth_diagnostic(
        code="auth.test.denied",
        outcome="denied",
        provider=AuthProvider.MOCK,
        details={
            "identity": _identity(secret_subject),
            "context": context,
            "authorization": "Bearer secret.jwt.token",
            "nested": {
                "provider_subject": secret_subject,
                "tg_id": 123456789,
                "ton_wallet_id": "EQ_SECRET_TON_WALLET",
                "google_id": "google-secret-subject",
                "apple_id": "apple-secret-subject",
                "fb_id": "facebook-secret-subject",
                "discord_id": "discord-secret-subject",
                "github_id": "github-secret-subject",
                "session_id": secret_session,
                "proof": "signed-proof",
                "safe": "visible",
            },
            "message": "token=plain-secret safe=visible",
        },
    )
    rendered = str(diagnostic)
    for secret in (
        secret_subject,
        secret_session,
        "secret.jwt.token",
        "signed-proof",
        "plain-secret",
        "123456789",
        "EQ_SECRET_TON_WALLET",
        "google-secret-subject",
        "apple-secret-subject",
        "facebook-secret-subject",
        "discord-secret-subject",
        "github-secret-subject",
    ):
        assert secret not in rendered
    assert diagnostic["детали"]["nested"]["safe"] == "visible"
    assert AUTH_REDACTION_MASK in rendered


def test_auth_redaction_имеет_depth_и_size_limits() -> None:
    nested: dict[str, object] = {}
    cursor = nested
    for index in range(12):
        child: dict[str, object] = {"index": index}
        cursor["child"] = child
        cursor = child
    safe = redact_auth_diagnostic(nested)
    assert "<depth-limit>" in str(safe)

    many = {f"safe_{index}": index for index in range(100)}
    bounded = redact_auth_diagnostic(many)
    assert isinstance(bounded, dict)
    assert bounded["<truncated>"] is True
    assert len(bounded) == 65


def test_global_logging_filter_редактирует_auth_fields() -> None:
    record = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        1,
        "auth diagnostic",
        (),
        None,
    )
    record.provider_subject = "subject-secret"
    record.session_id = "session-secret"
    record.raw_input = {"access_token": "token-secret"}

    assert RedactingFilter(SimpleNamespace()).filter(record) is True
    assert record.provider_subject == "****"
    assert record.session_id == "****"
    assert record.raw_input == "****"


def test_machine_contract_фиксирует_no_side_effects() -> None:
    contract = build_auth_context_contract()
    assert contract["внутренний_context"]["tg_id"] is False
    assert contract["endpoint_response"]["tg_id"] is False
    assert contract["resolver_interface"]["создаёт_account"] is False
    assert contract["resolver_interface"]["открывает_session"] is False
    assert contract["resolver_interface"]["auto_merge"] is False
    assert contract["resolver_interface"]["database_ddl"] is False


def test_error_codes_включают_contract_failures() -> None:
    assert "auth.context_invalid" in AUTH_PROVIDER_ERROR_CODES
    assert "auth.identity_resolution_invalid" in (
        AUTH_PROVIDER_ERROR_CODES
    )
