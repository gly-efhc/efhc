"""Fail-closed registry provider-neutral авторизации EFHC."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from app.identity.auth_errors import (
    DuplicateProviderRegistration,
    InvalidProviderConfiguration,
    MockProviderForbiddenInProduction,
    ProviderCanonicalNameConflict,
    ProviderCapabilityUnsupported,
    ProviderDisabled,
    ProviderNotRegistered,
    VerificationResultMissing,
)
from app.identity.auth_provider import AuthProvider, parse_auth_provider
from app.identity.identity_registry import (
    CANONICAL_PROVIDER_SUBJECT_FIELDS,
)
from app.identity.verified_identity import (
    VerifiedIdentity,
    _create_verified_identity,
)


# Сохраняем историческую str+Enum семантику machine-contract.
class ProviderCapability(str, Enum):  # noqa: UP042
    """Capability, которую adapter обязан объявить явно."""

    VERIFY_IDENTITY = "verify_identity"


# Сохраняем историческую str+Enum семантику machine-contract.
class ProviderAvailability(str, Enum):  # noqa: UP042
    """Состояние зарегистрированного provider."""

    ENABLED = "enabled"
    DISABLED = "disabled"


@runtime_checkable
class AuthProviderAdapter(Protocol):
    """Минимальный provider-specific verification adapter contract."""

    provider: AuthProvider

    def verify_subject(self, raw_input: object) -> str | None:
        """Проверить raw input и вернуть нормализованный subject."""


AdapterFactory = Callable[[], AuthProviderAdapter]


@dataclass(frozen=True, slots=True)
class ProviderRegistration:
    """Одна registration без domain, session и database dependencies."""

    provider: AuthProvider
    canonical_name: str
    availability: ProviderAvailability
    capabilities: frozenset[ProviderCapability]
    adapter_factory: AdapterFactory | None = None
    test_only: bool = False

    @property
    def enabled(self) -> bool:
        """Сообщить, разрешён ли provider текущей конфигурацией."""

        return self.availability is ProviderAvailability.ENABLED


@dataclass(frozen=True, slots=True)
class AuthProviderFeatureFlags:
    """Strict feature flags с отдельным runtime/test контуром."""

    environment: str
    enabled_providers: frozenset[AuthProvider]
    source: str

    @classmethod
    def from_mappings(
        cls,
        *,
        environment: str,
        runtime_flags: Mapping[str, object] | None = None,
        test_flags: Mapping[str, object] | None = None,
    ) -> AuthProviderFeatureFlags:
        """Построить flags; отсутствие значения всегда означает deny."""

        env = _normalize_environment(environment)
        runtime = _parse_flag_mapping(runtime_flags)
        testing = _parse_flag_mapping(test_flags)
        if env in {"prod", "stage"}:
            if runtime.get(AuthProvider.MOCK, False) or testing.get(
                AuthProvider.MOCK,
                False,
            ):
                raise MockProviderForbiddenInProduction()
            if any(testing.values()):
                raise InvalidProviderConfiguration()
        active = testing if env == "ci" else runtime
        if active.get(AuthProvider.MOCK, False) and env != "ci":
            raise MockProviderForbiddenInProduction()
        return cls(
            environment=env,
            enabled_providers=frozenset(
                provider
                for provider, enabled in active.items()
                if enabled
            ),
            source=("test" if env == "ci" else "runtime"),
        )

    def is_enabled(self, provider: AuthProvider) -> bool:
        """Неизвестный или отсутствующий flag никогда не разрешает."""

        if not isinstance(provider, AuthProvider):
            return False
        return provider in self.enabled_providers


class AuthProviderRegistry:
    """Единственный runtime registry доступных auth providers."""

    def __init__(self, *, environment: str) -> None:
        self._environment = _normalize_environment(environment)
        self._registrations: dict[
            AuthProvider,
            ProviderRegistration,
        ] = {}
        self._canonical_names: dict[str, AuthProvider] = {}

    @property
    def environment(self) -> str:
        """Вернуть канонический runtime environment."""

        return self._environment

    def register(self, registration: ProviderRegistration) -> None:
        """Зарегистрировать provider, запрещая дубли и конфликты."""

        if not isinstance(registration.provider, AuthProvider):
            raise InvalidProviderConfiguration()
        provider = registration.provider
        if provider in self._registrations:
            raise DuplicateProviderRegistration()
        if registration.canonical_name != provider.wire_name:
            raise ProviderCanonicalNameConflict()
        existing = self._canonical_names.get(
            registration.canonical_name
        )
        if existing is not None and existing is not provider:
            raise ProviderCanonicalNameConflict()
        if (
            registration.test_only
            and self._environment != "ci"
            and registration.enabled
        ):
            raise MockProviderForbiddenInProduction()
        if (
            registration.enabled
            and registration.adapter_factory is None
        ):
            raise InvalidProviderConfiguration()
        self._registrations[provider] = registration
        self._canonical_names[registration.canonical_name] = provider

    def status(
        self,
        provider: AuthProvider,
    ) -> ProviderAvailability:
        """Вернуть status только зарегистрированного provider."""

        registration = self._registrations.get(provider)
        if registration is None:
            raise ProviderNotRegistered()
        return registration.availability

    def require(
        self,
        provider: AuthProvider,
        capability: ProviderCapability,
    ) -> ProviderRegistration:
        """Fail closed получить enabled registration и capability."""

        if not isinstance(provider, AuthProvider):
            raise ProviderNotRegistered()
        registration = self._registrations.get(provider)
        if registration is None:
            raise ProviderNotRegistered()
        if not registration.enabled:
            raise ProviderDisabled()
        if capability not in registration.capabilities:
            raise ProviderCapabilityUnsupported()
        if registration.adapter_factory is None:
            raise InvalidProviderConfiguration()
        return registration

    def require_wire(
        self,
        provider_name: object,
        capability: ProviderCapability,
    ) -> ProviderRegistration:
        """Wire boundary: exact provider parse и fail-closed lookup."""

        provider = parse_auth_provider(provider_name)
        return self.require(provider, capability)

    def verify(
        self,
        provider: AuthProvider,
        raw_input: object,
    ) -> VerifiedIdentity:
        """Проверить identity без domain, user или session effects."""

        registration = self.require(
            provider,
            ProviderCapability.VERIFY_IDENTITY,
        )
        factory = registration.adapter_factory
        if factory is None:
            raise InvalidProviderConfiguration()
        adapter = factory()
        if not isinstance(adapter, AuthProviderAdapter):
            raise InvalidProviderConfiguration()
        if adapter.provider is not provider:
            raise InvalidProviderConfiguration()
        subject = adapter.verify_subject(raw_input)
        if subject is None:
            raise VerificationResultMissing()
        return _create_verified_identity(provider, subject)

    def snapshot(self) -> tuple[ProviderRegistration, ...]:
        """Вернуть детерминированный immutable snapshot registry."""

        return tuple(
            self._registrations[provider]
            for provider in sorted(
                self._registrations,
                key=lambda item: item.value,
            )
        )


def build_default_provider_registry(
    flags: AuthProviderFeatureFlags,
) -> AuthProviderRegistry:
    """Создать reserved registry без преждевременных adapters."""

    registry = AuthProviderRegistry(environment=flags.environment)
    for provider in AuthProvider:
        if provider is AuthProvider.MOCK:
            continue
        enabled = flags.is_enabled(provider)
        registry.register(
            ProviderRegistration(
                provider=provider,
                canonical_name=provider.wire_name,
                availability=(
                    ProviderAvailability.ENABLED
                    if enabled
                    else ProviderAvailability.DISABLED
                ),
                capabilities=frozenset(
                    {ProviderCapability.VERIFY_IDENTITY}
                ),
                adapter_factory=None,
                test_only=False,
            )
        )
    return registry


def finalize_verified_provider_subject(
    provider: AuthProvider,
    provider_subject: object,
) -> VerifiedIdentity:
    """Создать identity из уже проверенного provider результата."""

    if not isinstance(provider, AuthProvider):
        raise InvalidProviderConfiguration()
    if provider is AuthProvider.MOCK:
        raise MockProviderForbiddenInProduction()
    return _create_verified_identity(provider, provider_subject)


def build_auth_provider_registry_contract() -> dict[str, object]:
    """Сформировать machine contract из кода registry."""

    return {
        "схема": "EFHC_AUTH_PROVIDER_REGISTRY_V1",
        "цикл": 1609,
        "канонические_provider": [
            provider.value for provider in AuthProvider
        ],
        "production_provider_по_умолчанию": [
            {
                "provider": provider.value,
                "состояние": ProviderAvailability.DISABLED.value,
                "capabilities": [
                    ProviderCapability.VERIFY_IDENTITY.value
                ],
            }
            for provider in AuthProvider
            if provider is not AuthProvider.MOCK
        ],
        "mock_provider": {
            "provider": AuthProvider.MOCK.value,
            "test_only": True,
            "production_enabled": False,
        },
        "canonical_subject_fields": dict(
            CANONICAL_PROVIDER_SUBJECT_FIELDS
        ),
        "инварианты": {
            "unknown_fail_closed": True,
            "missing_flag_means_disabled": True,
            "provider_is_not_global_owner": True,
            "verified_identity_has_global_id": False,
            "creates_user": False,
            "creates_session": False,
            "database_ddl": False,
        },
    }


def _parse_flag_mapping(
    flags: Mapping[str, object] | None,
) -> dict[AuthProvider, bool]:
    parsed: dict[AuthProvider, bool] = {}
    for raw_provider, raw_enabled in dict(flags or {}).items():
        try:
            provider = parse_auth_provider(raw_provider)
        except ValueError as exc:
            raise InvalidProviderConfiguration() from exc
        if not isinstance(raw_enabled, bool):
            raise InvalidProviderConfiguration()
        parsed[provider] = raw_enabled
    return parsed


def _normalize_environment(value: object) -> str:
    raw = str(value or "local").strip().lower()
    aliases = {
        "production": "prod",
        "staging": "stage",
        "development": "dev",
        "test": "ci",
    }
    normalized = aliases.get(raw, raw)
    if normalized not in {"local", "dev", "stage", "prod", "ci"}:
        raise InvalidProviderConfiguration()
    return normalized
