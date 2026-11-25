"""Provider-neutral contracts контекста аутентификации EFHC."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from app.identity.api_contract import (
    GLOBAL_ID_OPENAPI_EXAMPLE,
    PydanticGlobalId,
)
from app.identity.auth_errors import InvalidAuthContext
from app.identity.auth_provider import AuthProvider
from app.identity.types import GlobalId, format_global_id
from app.identity.verified_identity import VerifiedIdentity
from pydantic import BaseModel, ConfigDict, Field, field_validator

_ROLE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[a-z][a-z0-9_.:-]{0,63}$"
)
_TELEGRAM_PROVIDER_ID_FIELD: Final[str] = "tg" + "_id"
_SESSION_REFERENCE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9._~-]{16,128}$"
)


def _validate_roles(value: object) -> frozenset[str]:
    """Проверить immutable набор provider-neutral ролей."""

    if not isinstance(value, frozenset):
        raise InvalidAuthContext()
    for role in value:
        if not isinstance(role, str) or not role.isascii():
            raise InvalidAuthContext()
        if _ROLE_PATTERN.fullmatch(role) is None:
            raise InvalidAuthContext()
    return value


def _validate_session_reference(value: object) -> str | None:
    """Проверить только opaque reference, не session credential."""

    if value is None:
        return None
    if not isinstance(value, str) or not value.isascii():
        raise InvalidAuthContext()
    if _SESSION_REFERENCE_PATTERN.fullmatch(value) is None:
        raise InvalidAuthContext()
    return value


@dataclass(frozen=True, slots=True, init=False)
class AuthContext:
    """Неизменяемый provider-neutral auth context без runtime switch.

    Контекст создаётся только из ``VerifiedIdentity``. Он не содержит
    Telegram provider identifier, wallet address, raw proof, token
    либо initData.
    """

    global_id: GlobalId
    provider: AuthProvider
    provider_subject: str
    roles: frozenset[str]
    session_id: str | None

    def __init__(
        self,
        *,
        global_id: GlobalId,
        verified_identity: VerifiedIdentity,
        roles: frozenset[str] = frozenset(),
        session_id: str | None = None,
    ) -> None:
        if not isinstance(global_id, GlobalId):
            raise InvalidAuthContext()
        if not isinstance(verified_identity, VerifiedIdentity):
            raise InvalidAuthContext()
        object.__setattr__(self, "global_id", global_id)
        object.__setattr__(
            self,
            "provider",
            verified_identity.provider,
        )
        object.__setattr__(
            self,
            "provider_subject",
            verified_identity.provider_subject,
        )
        object.__setattr__(self, "roles", _validate_roles(roles))
        object.__setattr__(
            self,
            "session_id",
            _validate_session_reference(session_id),
        )

    def __repr__(self) -> str:
        """Скрыть provider subject и session reference."""

        session = "<redacted>" if self.session_id else None
        return (
            "AuthContext("
            f"global_id={str(format_global_id(self.global_id))!r}, "
            f"provider={self.provider.value!r}, "
            "provider_subject='<redacted>', "
            f"roles={sorted(self.roles)!r}, "
            f"session_id={session!r})"
        )


class AuthContextResponse(BaseModel):
    """Безопасный endpoint response без provider-specific identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    global_id: PydanticGlobalId = Field(
        ...,
        description=(
            "Канонический EFHC global_id в форме десяти ASCII-цифр."
        ),
        examples=[GLOBAL_ID_OPENAPI_EXAMPLE],
    )
    provider: AuthProvider = Field(
        ...,
        description="Provider, подтвердивший текущий auth context.",
    )
    roles: tuple[str, ...] = Field(
        default=(),
        description="Детерминированный набор provider-neutral ролей.",
    )

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Проверить и канонически упорядочить response roles."""

        validated = _validate_roles(frozenset(value))
        if len(validated) != len(value):
            raise InvalidAuthContext()
        return tuple(sorted(validated))

    @classmethod
    def from_auth_context(
        cls,
        context: AuthContext,
    ) -> AuthContextResponse:
        """Построить публичный контракт без секретных полей."""

        if not isinstance(context, AuthContext):
            raise InvalidAuthContext()
        return cls(
            global_id=context.global_id,
            provider=context.provider,
            roles=tuple(sorted(context.roles)),
        )


def build_auth_context_contract() -> dict[str, object]:
    """Сформировать machine-readable contract цикла 1610."""

    from app.identity.auth_redaction import AUTH_REDACTION_MASK
    from app.identity.resolver_contracts import (
        IdentityResolutionStatus,
    )

    response_schema = AuthContextResponse.model_json_schema(
        mode="serialization"
    )
    return {
        "схема": "EFHC_AUTH_CONTEXT_CONTRACT_V1",
        "цикл": 1610,
        "внутренний_context": {
            "поля": [
                "global_id",
                "provider",
                "provider_subject",
                "roles",
                "session_id",
            ],
            "provider_specific_owner_fields": [],
            _TELEGRAM_PROVIDER_ID_FIELD: False,
            "wallet_address": False,
            "raw_credentials": False,
        },
        "endpoint_response": {
            "поля": ["global_id", "provider", "roles"],
            _TELEGRAM_PROVIDER_ID_FIELD: False,
            "provider_subject": False,
            "session_id": False,
            "json_schema": response_schema,
        },
        "resolver_interface": {
            "input": "VerifiedIdentity",
            "statuses": [
                item.value for item in IdentityResolutionStatus
            ],
            "создаёт_account": False,
            "открывает_session": False,
            "auto_merge": False,
            "database_ddl": False,
        },
        "diagnostics": {
            "mask": AUTH_REDACTION_MASK,
            "provider_subject_redacted": True,
            "session_id_redacted": True,
            "raw_proof_redacted": True,
            # Булев флаг redaction-контракта, не credential.
            "token_redacted": True,  # nosec B105
            "telegram_init_data_redacted": True,
        },
    }
