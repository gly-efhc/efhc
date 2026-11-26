"""Канонический строгий тип auth provider EFHC."""

from __future__ import annotations

from enum import Enum
from typing import TypeGuard

from app.identity.auth_errors import InvalidAuthProviderIdentifier


# Сохраняем историческую str+Enum семантику wire-контракта.
class AuthProvider(str, Enum):  # noqa: UP042
    """Закрытый набор providers из активного identity SSOT."""

    TELEGRAM = "telegram"
    TON = "ton"
    GOOGLE = "google"
    APPLE = "apple"
    FACEBOOK = "facebook"
    DISCORD = "discord"
    GITHUB = "github"
    MOCK = "mock"

    @classmethod
    def from_wire(cls, value: object) -> AuthProvider:
        """Разобрать exact ASCII wire value без нормализации."""

        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise InvalidAuthProviderIdentifier()
        if not value or not value.isascii():
            raise InvalidAuthProviderIdentifier()
        try:
            provider = cls(value)
        except ValueError as exc:
            raise InvalidAuthProviderIdentifier() from exc
        if provider.value != value:
            raise InvalidAuthProviderIdentifier()
        return provider

    @property
    def wire_name(self) -> str:
        """Вернуть каноническое wire-представление provider."""

        return self.value


def parse_auth_provider(value: object) -> AuthProvider:
    """Явная wire boundary для канонического provider identifier."""

    return AuthProvider.from_wire(value)


def is_auth_provider(value: object) -> TypeGuard[AuthProvider]:
    """Проверить уже созданный nominal provider identifier."""

    return isinstance(value, AuthProvider)
