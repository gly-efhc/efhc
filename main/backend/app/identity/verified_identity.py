"""Provider-neutral результат успешной внешней проверки identity."""

from __future__ import annotations

from dataclasses import dataclass

from app.identity.auth_errors import (
    MalformedProviderSubject,
    VerificationResultMissing,
)
from app.identity.auth_provider import AuthProvider

_VERIFIED_IDENTITY_MARKER = object()
_MAX_PROVIDER_SUBJECT_LENGTH = 1024


def _validate_provider_subject_boundary(value: object) -> str:
    """Проверить общий boundary без provider-specific нормализации."""

    if not isinstance(value, str):
        raise MalformedProviderSubject()
    if not value or not value.strip():
        raise MalformedProviderSubject()
    if len(value) > _MAX_PROVIDER_SUBJECT_LENGTH:
        raise MalformedProviderSubject()
    if any(ord(character) < 32 for character in value):
        raise MalformedProviderSubject()
    return value


@dataclass(frozen=True, slots=True, init=False)
class VerifiedIdentity:
    """Identity после adapter verification через registry."""

    provider: AuthProvider
    provider_subject: str

    def __init__(
        self,
        *,
        provider: AuthProvider,
        provider_subject: str,
        _verification_marker: object | None = None,
    ) -> None:
        if _verification_marker is not _VERIFIED_IDENTITY_MARKER:
            raise VerificationResultMissing()
        if not isinstance(provider, AuthProvider):
            raise VerificationResultMissing()
        subject = _validate_provider_subject_boundary(provider_subject)
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "provider_subject", subject)

    def __repr__(self) -> str:
        """Не раскрывать provider subject и raw verification data."""

        return (
            "VerifiedIdentity("
            f"provider={self.provider.value!r}, "
            "provider_subject='<redacted>')"
        )


def _create_verified_identity(
    provider: AuthProvider,
    provider_subject: object,
) -> VerifiedIdentity:
    """Внутренняя factory, доступная только provider registry."""

    subject = _validate_provider_subject_boundary(provider_subject)
    return VerifiedIdentity(
        provider=provider,
        provider_subject=subject,
        _verification_marker=_VERIFIED_IDENTITY_MARKER,
    )


def _restore_verified_identity_from_storage(
    provider: AuthProvider,
    provider_subject: object,
) -> VerifiedIdentity:
    """Восстановить identity только из доверенной PostgreSQL-строки."""

    subject = _validate_provider_subject_boundary(provider_subject)
    return VerifiedIdentity(
        provider=provider,
        provider_subject=subject,
        _verification_marker=_VERIFIED_IDENTITY_MARKER,
    )
