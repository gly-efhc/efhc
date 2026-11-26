"""TON login challenge foundation цикла 1615.

Этот модуль не проверяет подпись TON Proof, не создаёт account/session и
не зависит от Telegram. Он только выдаёт one-time challenge через уже
существующий ``auth_challenges`` storage цикла 1613.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Protocol
from urllib.parse import urlsplit
from uuid import UUID

from app.identity.auth_provider import AuthProvider
from app.identity.auth_runtime_services import (
    AuthChallengeService,
    IssuedAuthChallenge,
)
from app.identity.auth_runtime_storage_contract import (
    AUTH_DOMAIN_MAX_LENGTH,
)

TON_LOGIN_PURPOSE: Final[str] = "ton.login"
TON_LOGIN_CHALLENGE_TTL: Final[timedelta] = timedelta(minutes=10)
TON_LOGIN_CANONICAL_FORMAT: Final[str] = (
    "<workchain>:<64 lowercase hex account_id>"
)


class TonLoginDomainError(ValueError):
    """Публичный domain TON Proof не определён однозначно."""

    code = "auth.ton_domain_invalid"
    message = "Domain TON login недействителен"

    def __init__(self, reason: str = "DOMAIN_INVALID") -> None:
        self.reason = reason
        super().__init__(self.message)


class ChallengeIssuer(Protocol):
    """Минимальный порт выдачи one-time challenge."""

    async def issue(
        self,
        *,
        provider: AuthProvider,
        purpose: str,
        domain: str,
        ttl: timedelta,
        provider_tenant: str = "default",
    ) -> IssuedAuthChallenge:
        """Выдать challenge без provider subject.

        Метод не создаёт account side effects.
        """


@dataclass(frozen=True, slots=True)
class IssuedTonLoginChallenge:
    """Публичный результат TON login challenge endpoint."""

    challenge_id: UUID
    payload: str
    expires_at: datetime
    domain: str
    provider: str = AuthProvider.TON.value
    purpose: str = TON_LOGIN_PURPOSE

    def __repr__(self) -> str:
        return (
            "IssuedTonLoginChallenge("
            f"challenge_id={self.challenge_id!r}, "
            "payload='<redacted>', "
            f"domain={self.domain!r})"
        )


def canonicalize_ton_login_domain(value: object) -> str:
    """Вернуть lowercase ASCII hostname.

    Scheme, path, query и fragment не входят в результат.
    """

    if not isinstance(value, str):
        raise TonLoginDomainError("DOMAIN_TYPE_INVALID")
    raw = value.strip()
    if not raw or raw != value or not raw.isascii():
        raise TonLoginDomainError("DOMAIN_INVALID")
    parsed = urlsplit(raw if "://" in raw else f"//{raw}")
    if parsed.username or parsed.password:
        raise TonLoginDomainError("DOMAIN_CREDENTIALS_FORBIDDEN")
    if parsed.query or parsed.fragment:
        raise TonLoginDomainError("DOMAIN_SUFFIX_FORBIDDEN")
    if parsed.path not in {"", "/"}:
        raise TonLoginDomainError("DOMAIN_PATH_FORBIDDEN")
    hostname = parsed.hostname
    if hostname is None:
        raise TonLoginDomainError("DOMAIN_INVALID")
    canonical = hostname.rstrip(".").lower()
    if not canonical or len(canonical) > AUTH_DOMAIN_MAX_LENGTH:
        raise TonLoginDomainError("DOMAIN_INVALID")
    try:
        canonical.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise TonLoginDomainError("DOMAIN_IDNA_INVALID") from exc
    return canonical


def resolve_ton_login_domain(
    *,
    environment: object,
    app_url: object,
    frontend_url: object,
    request_hostname: object,
) -> str:
    """Выбрать authoritative TON login domain.

    Production fallback завершается fail closed.
    """

    env = str(environment or "local").strip().lower()
    configured = [
        value
        for value in (app_url, frontend_url)
        if isinstance(value, str) and value.strip()
    ]
    if configured:
        return canonicalize_ton_login_domain(configured[0])
    if env in {"prod", "production", "stage", "staging"}:
        raise TonLoginDomainError("CONFIGURED_DOMAIN_REQUIRED")
    return canonicalize_ton_login_domain(request_hostname)


class TonLoginChallengeService:
    """Выдать TON login challenge через provider-neutral storage."""

    def __init__(self, challenge_service: ChallengeIssuer) -> None:
        self._challenge_service = challenge_service

    @classmethod
    def from_auth_service(
        cls,
        challenge_service: AuthChallengeService,
    ) -> TonLoginChallengeService:
        """Создать typed wrapper над каноническим auth-core service."""

        return cls(challenge_service)

    async def issue(self, *, domain: object) -> IssuedTonLoginChallenge:
        domain_value = canonicalize_ton_login_domain(domain)
        issued = await self._challenge_service.issue(
            provider=AuthProvider.TON,
            purpose=TON_LOGIN_PURPOSE,
            domain=domain_value,
            ttl=TON_LOGIN_CHALLENGE_TTL,
        )
        return IssuedTonLoginChallenge(
            challenge_id=issued.challenge_id,
            payload=issued.token,
            expires_at=issued.expires_at,
            domain=domain_value,
        )


def build_ton_login_challenge_contract() -> dict[str, object]:
    """Сформировать machine contract TON login foundation."""

    return {
        "схема": "EFHC_TON_LOGIN_CHALLENGE_V1",
        "цикл": 1615,
        "provider": AuthProvider.TON.value,
        "purpose": TON_LOGIN_PURPOSE,
        "ttl_секунд": int(TON_LOGIN_CHALLENGE_TTL.total_seconds()),
        "canonical_address_format": TON_LOGIN_CANONICAL_FORMAT,
        "provider_subject_field": "ton_wallet_id",
        "provider_subject_semantics": "TON wallet address",
        "инварианты": {
            "telegram_dependency": False,
            "tg_id_field": False,
            "raw_challenge_stored": False,
            "challenge_hash_storage": True,
            "one_time_consumption": True,
            "rate_limited_before_insert": True,
            "bounded_storage_cleanup": True,
            "creates_account": False,
            "creates_identity": False,
            "creates_session": False,
            "verifies_ton_proof": False,
        },
    }


__all__ = [
    "IssuedTonLoginChallenge",
    "TON_LOGIN_CANONICAL_FORMAT",
    "TON_LOGIN_CHALLENGE_TTL",
    "TON_LOGIN_PURPOSE",
    "TonLoginChallengeService",
    "TonLoginDomainError",
    "build_ton_login_challenge_contract",
    "canonicalize_ton_login_domain",
    "resolve_ton_login_domain",
]
