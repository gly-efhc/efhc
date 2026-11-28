"""Стабильная таксономия ошибок auth provider foundation.

Ошибки не принимают raw credentials и не включают proof, token,
Telegram initData либо provider-specific secrets в текст и payload.
"""

from __future__ import annotations


class AuthProviderError(ValueError):
    """Базовая машинно-различимая ошибка provider-neutral auth."""

    code = "auth.provider_error"
    message = "Ошибка provider-neutral авторизации"

    def __init__(self) -> None:
        super().__init__(self.message)

    def as_dict(self) -> dict[str, str]:
        """Вернуть безопасный machine payload на русском языке."""

        return {
            "код": self.code,
            "сообщение": self.message,
        }


class InvalidAuthProviderIdentifier(AuthProviderError):
    """Provider identifier не соответствует каноническому набору."""

    code = "auth.provider_identifier_invalid"
    message = "Идентификатор auth provider недействителен"


class ProviderNotRegistered(AuthProviderError):
    """Provider отсутствует в активном registry."""

    code = "auth.provider_not_registered"
    message = "Auth provider не зарегистрирован"


class ProviderDisabled(AuthProviderError):
    """Provider зарегистрирован, но выключен feature flag."""

    code = "auth.provider_disabled"
    message = "Auth provider отключён"


class DuplicateProviderRegistration(AuthProviderError):
    """Повторная регистрация provider запрещена."""

    code = "auth.provider_duplicate_registration"
    message = "Повторная регистрация auth provider запрещена"


class ProviderCanonicalNameConflict(AuthProviderError):
    """Canonical name не совпадает с nominal provider identifier."""

    code = "auth.provider_canonical_name_conflict"
    message = "Canonical name auth provider конфликтует с registry"


class VerificationResultMissing(AuthProviderError):
    """Adapter не вернул результат успешной проверки."""

    code = "auth.verification_result_missing"
    message = "Результат проверки provider identity отсутствует"


class MalformedProviderSubject(AuthProviderError):
    """Проверенный provider subject нарушает общий boundary."""

    code = "auth.provider_subject_malformed"
    message = "Provider subject имеет недопустимый формат"


class ProviderCapabilityUnsupported(AuthProviderError):
    """Запрошенная capability не объявлена registration."""

    code = "auth.provider_capability_unsupported"
    message = "Auth provider не поддерживает требуемую capability"


class InvalidProviderConfiguration(AuthProviderError):
    """Provider registry либо feature flags сконфигурированы неверно."""

    code = "auth.provider_configuration_invalid"
    message = "Конфигурация auth providers недействительна"


class MockProviderForbiddenInProduction(AuthProviderError):
    """Mock provider запрещён вне явного test environment."""

    code = "auth.mock_provider_forbidden_in_production"
    message = "Mock auth provider запрещён вне test environment"


class InvalidAuthContext(AuthProviderError):
    """AuthContext нарушает provider-neutral contract."""

    code = "auth.context_invalid"
    message = "AuthContext имеет недопустимый состав"


class InvalidIdentityResolution(AuthProviderError):
    """Результат resolver interface нарушает fail-closed contract."""

    code = "auth.identity_resolution_invalid"
    message = "Результат IdentityResolver недействителен"


class InvalidAuthRuntimeInput(AuthProviderError):
    """Вход challenge/session/role нарушает auth-core contract."""

    code = "auth.runtime_input_invalid"
    message = "Входные данные auth-core недействительны"


class AuthChallengeNotConsumable(AuthProviderError):
    """Challenge отсутствует, истёк либо уже завершён."""

    code = "auth.challenge_not_consumable"
    message = "Auth challenge недоступен для использования"


class AuthSessionNotActive(AuthProviderError):
    """Session отсутствует, истекла либо отозвана."""

    code = "auth.session_not_active"
    message = "Auth session недействительна"


class AuthChallengeRateLimited(AuthProviderError):
    """Выдача нового auth challenge временно ограничена."""

    code = "auth.challenge_rate_limited"
    message = "Слишком много запросов auth challenge"


class AuthRoleDenied(AuthProviderError):
    """Текущий auth context не содержит требуемую роль."""

    code = "auth.role_denied"
    message = "Недостаточно прав для выполнения операции"


AUTH_RUNTIME_ERROR_CODES = (
    InvalidAuthRuntimeInput.code,
    AuthChallengeNotConsumable.code,
    AuthSessionNotActive.code,
    AuthChallengeRateLimited.code,
    AuthRoleDenied.code,
)
AUTH_PROVIDER_ERROR_CODES = (
    InvalidAuthProviderIdentifier.code,
    ProviderNotRegistered.code,
    ProviderDisabled.code,
    DuplicateProviderRegistration.code,
    ProviderCanonicalNameConflict.code,
    VerificationResultMissing.code,
    MalformedProviderSubject.code,
    ProviderCapabilityUnsupported.code,
    InvalidProviderConfiguration.code,
    MockProviderForbiddenInProduction.code,
    InvalidAuthContext.code,
    InvalidIdentityResolution.code,
    *AUTH_RUNTIME_ERROR_CODES,
)
