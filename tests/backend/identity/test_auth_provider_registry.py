"""Причинные unit/negative/boundary тесты цикла 1609."""

from __future__ import annotations

from dataclasses import fields

import pytest
from app.identity import (
    AuthProvider,
    AuthProviderFeatureFlags,
    AuthProviderRegistry,
    DuplicateProviderRegistration,
    GlobalId,
    InvalidAuthProviderIdentifier,
    InvalidProviderConfiguration,
    MalformedProviderSubject,
    MockProviderForbiddenInProduction,
    ProviderAvailability,
    ProviderCanonicalNameConflict,
    ProviderCapability,
    ProviderCapabilityUnsupported,
    ProviderDisabled,
    ProviderNotRegistered,
    ProviderRegistration,
    TelegramId,
    VerificationResultMissing,
    VerifiedIdentity,
    build_default_provider_registry,
    parse_auth_provider,
)
from tests.support.mock_auth_provider import MockAuthProviderAdapter


def _mock_registration(
    *,
    enabled: bool = True,
    capabilities: frozenset[ProviderCapability] | None = None,
) -> ProviderRegistration:
    return ProviderRegistration(
        provider=AuthProvider.MOCK,
        canonical_name="mock",
        availability=(
            ProviderAvailability.ENABLED
            if enabled
            else ProviderAvailability.DISABLED
        ),
        capabilities=(
            capabilities
            if capabilities is not None
            else frozenset({ProviderCapability.VERIFY_IDENTITY})
        ),
        adapter_factory=MockAuthProviderAdapter,
        test_only=True,
    )


def _test_registry() -> AuthProviderRegistry:
    registry = AuthProviderRegistry(environment="ci")
    registry.register(_mock_registration())
    return registry


def test_канонический_provider_identifier_принимается() -> None:
    assert parse_auth_provider("telegram") is AuthProvider.TELEGRAM
    assert parse_auth_provider(AuthProvider.TON) is (
        AuthProvider.TON
    )
    assert AuthProvider.TELEGRAM.wire_name == "telegram"
    assert parse_auth_provider("discord") is AuthProvider.DISCORD


@pytest.mark.parametrize(
    "value",
    [
        "",
        "unknown",
        "Telegram",
        " telegram",
        "telegram ",
        "teIegram",
        "ton_wallet",
        "tеlegram",
        "microsoft",
        "email",
        "phone",
        1,
        None,
    ],
)
def test_неизвестный_или_confusable_provider_отклоняется(
    value: object,
) -> None:
    with pytest.raises(InvalidAuthProviderIdentifier):
        parse_auth_provider(value)


def test_неподдержанный_provider_завершается_fail_closed() -> None:
    registry = AuthProviderRegistry(environment="ci")
    with pytest.raises(ProviderNotRegistered):
        registry.require(
            AuthProvider.TELEGRAM,
            ProviderCapability.VERIFY_IDENTITY,
        )
    with pytest.raises(InvalidAuthProviderIdentifier):
        registry.require_wire(
            "unsupported",
            ProviderCapability.VERIFY_IDENTITY,
        )


def test_отключённый_provider_отклоняется() -> None:
    registry = AuthProviderRegistry(environment="ci")
    registry.register(_mock_registration(enabled=False))
    with pytest.raises(ProviderDisabled):
        registry.verify(
            AuthProvider.MOCK,
            {"test_verification": True, "subject": "mock:1"},
        )


def test_duplicate_registration_отклоняется() -> None:
    registry = AuthProviderRegistry(environment="ci")
    registry.register(_mock_registration())
    with pytest.raises(DuplicateProviderRegistration):
        registry.register(_mock_registration())


def test_конфликт_canonical_name_отклоняется() -> None:
    registry = AuthProviderRegistry(environment="ci")
    registration = ProviderRegistration(
        provider=AuthProvider.MOCK,
        canonical_name="telegram",
        availability=ProviderAvailability.DISABLED,
        capabilities=frozenset(),
        adapter_factory=None,
        test_only=True,
    )
    with pytest.raises(ProviderCanonicalNameConflict):
        registry.register(registration)


def test_mock_provider_подключается_через_общий_contract() -> None:
    identity = _test_registry().verify(
        AuthProvider.MOCK,
        {
            "test_verification": True,
            "subject": "Case:SENSITIVE/01",
        },
    )
    assert identity.provider is AuthProvider.MOCK
    assert identity.provider_subject == "Case:SENSITIVE/01"


def test_mock_provider_требует_явную_test_verification() -> None:
    registry = _test_registry()
    with pytest.raises(VerificationResultMissing):
        registry.verify(
            AuthProvider.MOCK,
            {"test_verification": False, "subject": "mock:1"},
        )


def test_mock_provider_запрещён_в_production() -> None:
    flags = {"mock": True}
    with pytest.raises(MockProviderForbiddenInProduction):
        AuthProviderFeatureFlags.from_mappings(
            environment="prod",
            runtime_flags=flags,
        )
    registry = AuthProviderRegistry(environment="prod")
    with pytest.raises(MockProviderForbiddenInProduction):
        registry.register(_mock_registration())


def test_runtime_и_test_flags_разделены_явно() -> None:
    flags = AuthProviderFeatureFlags.from_mappings(
        environment="ci",
        runtime_flags={"telegram": True},
        test_flags={"mock": True},
    )
    assert flags.source == "test"
    assert flags.is_enabled(AuthProvider.MOCK) is True
    assert flags.is_enabled(AuthProvider.TELEGRAM) is False


def test_отсутствующий_flag_означает_disabled() -> None:
    flags = AuthProviderFeatureFlags.from_mappings(
        environment="local",
    )
    assert flags.enabled_providers == frozenset()
    registry = build_default_provider_registry(flags)
    assert registry.status(AuthProvider.TELEGRAM) is (
        ProviderAvailability.DISABLED
    )


def test_unknown_flag_и_не_bool_value_отклоняются() -> None:
    with pytest.raises(InvalidProviderConfiguration):
        AuthProviderFeatureFlags.from_mappings(
            environment="local",
            runtime_flags={"unknown": True},
        )
    with pytest.raises(InvalidProviderConfiguration):
        AuthProviderFeatureFlags.from_mappings(
            environment="local",
            runtime_flags={"telegram": "true"},
        )


def test_unverified_input_не_становится_verified_identity() -> None:
    with pytest.raises(VerificationResultMissing):
        VerifiedIdentity(
            provider=AuthProvider.TELEGRAM,
            provider_subject="123",
        )


def test_malformed_provider_subject_отклоняется() -> None:
    registry = _test_registry()
    with pytest.raises(MalformedProviderSubject):
        registry.verify(
            AuthProvider.MOCK,
            {"test_verification": True, "subject": "\x00secret"},
        )


def test_verified_identity_не_содержит_domain_ownership() -> None:
    names = {field.name for field in fields(VerifiedIdentity)}
    assert names == {"provider", "provider_subject"}
    assert "global_id" not in names
    assert "tg_id" not in names
    assert "user" not in names
    assert "session" not in names


def test_repr_не_раскрывает_subject_или_secrets() -> None:
    secret = "VERY_SECRET_TOKEN_AND_INIT_DATA"
    identity = _test_registry().verify(
        AuthProvider.MOCK,
        {"test_verification": True, "subject": secret},
    )
    rendered = repr(identity)
    assert secret not in rendered
    assert "<redacted>" in rendered
    assert not hasattr(identity, "raw_input")
    assert not hasattr(identity, "token")
    assert not hasattr(identity, "proof")


def test_provider_capability_проверяется_fail_closed() -> None:
    registry = AuthProviderRegistry(environment="ci")
    registry.register(
        _mock_registration(capabilities=frozenset())
    )
    with pytest.raises(ProviderCapabilityUnsupported):
        registry.verify(
            AuthProvider.MOCK,
            {"test_verification": True, "subject": "mock:1"},
        )


def test_global_id_и_telegram_id_остаются_несовместимыми() -> None:
    assert GlobalId(42) != TelegramId(42)
    assert AuthProvider.TELEGRAM.value != "global_id"
