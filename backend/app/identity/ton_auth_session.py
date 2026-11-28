"""Атомарная выдача TON auth session цикла 1618."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Final

from app.identity.auth_errors import (
    AuthSessionNotActive,
    InvalidAuthRuntimeInput,
)
from app.identity.auth_runtime_services import (
    AuthSessionService,
    IssuedAuthSession,
)
from app.identity.ton_account_registration import (
    TonAccountRegistration,
    TonAccountRegistrationError,
    TonAccountRegistrationService,
)
from app.identity.ton_proof_verification import VerifiedTonProof
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

TON_AUTH_SESSION_TTL: Final[timedelta] = timedelta(days=30)


class TonAuthSessionError(ValueError):
    """TON session flow завершён без выдачи credential."""

    code = "auth.ton_session_failed"
    message = "TON auth session не может быть выдана"

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self.message)


@dataclass(frozen=True, slots=True)
class TonAuthSessionResult:
    """Результат account resolution и одноразовой выдачи token."""

    account: TonAccountRegistration
    session: IssuedAuthSession

    def __repr__(self) -> str:
        return (
            "TonAuthSessionResult("
            f"account={self.account!r}, "
            "session='<redacted>')"
        )


class TonAuthSessionService:
    """Создать account/identity/binding/session одной транзакцией."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        if not isinstance(session_factory, async_sessionmaker):
            raise TonAuthSessionError("SERVICE_CONFIG_INVALID")
        self._session_factory = session_factory
        self._account_service = TonAccountRegistrationService(
            session_factory
        )
        self._session_service = AuthSessionService(session_factory)

    async def login(
        self,
        proof: VerifiedTonProof,
        *,
        referral_start_param: str | None = None,
    ) -> TonAuthSessionResult:
        """Разрешить TON account и выдать hashed session атомарно."""

        if not isinstance(proof, VerifiedTonProof):
            raise TonAuthSessionError("PROOF_REQUIRED")
        try:
            async with (
                self._session_factory() as session,
                session.begin(),
            ):
                account = await (
                    self._account_service
                    .register_or_resolve_in_transaction(
                        session,
                        proof,
                        referral_start_param=referral_start_param,
                    )
                )
                issue = self._session_service.issue_in_transaction
                issued = await issue(
                    session,
                    global_id=account.global_id,
                    identity_id=account.identity_id,
                    ttl=TON_AUTH_SESSION_TTL,
                )
                return TonAuthSessionResult(account, issued)
        except TonAccountRegistrationError:
            raise
        except IntegrityError as exc:
            raise TonAuthSessionError("STORAGE_CONFLICT") from exc
        except (
            AuthSessionNotActive,
            InvalidAuthRuntimeInput,
        ) as exc:
            raise TonAuthSessionError("SESSION_ISSUE_DENIED") from exc


def build_ton_auth_session_contract() -> dict[str, object]:
    """Сформировать machine contract цикла 1618."""

    return {
        "схема": "EFHC_TON_AUTH_SESSION_V1",
        "цикл": 1618,
        "атомарность": {
            "account_identity_binding_session": True,
            "transaction_owner": "TonAuthSessionService",
        },
        "session": {
            "server_side": True,
            "raw_token_stored": False,  # nosec B105
            "token_returned_once": True,  # nosec B105
            "ttl_seconds": int(TON_AUTH_SESSION_TTL.total_seconds()),
            "logout_revokes": True,
        },
        "referral_transport": {
            "cycle": 1638,
            "normalized_param_accepted": True,
            "new_account_consumer": "AccountRegistrationService",
        },
        "frontend_transport": {
            "authorization_scheme": "Bearer",
            "storage": "sessionStorage",
            "global_id_as_javascript_number": False,
        },
        "запреты": {
            "telegram_dependency": True,
            "synthetic_provider_identifier": True,
            "financial_update": True,
            "legacy_ton_adapter": True,
        },
    }


__all__ = [
    "TON_AUTH_SESSION_TTL",
    "TonAuthSessionError",
    "TonAuthSessionResult",
    "TonAuthSessionService",
    "build_ton_auth_session_contract",
]
