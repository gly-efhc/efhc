"""Канонический storage-contract auth-core цикла 1613."""

from __future__ import annotations

from enum import Enum
from types import MappingProxyType
from typing import Final

AUTH_TABLE_SCHEMA: Final = "efhc_core"
AUTH_CHALLENGE_TABLE: Final = "auth_challenges"
AUTH_SESSION_TABLE: Final = "auth_sessions"
USER_ROLE_TABLE: Final = "user_roles"
AUTH_HASH_HEX_LENGTH: Final = 64
AUTH_PROVIDER_MAX_LENGTH: Final = 32
AUTH_TENANT_MAX_LENGTH: Final = 128
AUTH_PURPOSE_MAX_LENGTH: Final = 64
AUTH_DOMAIN_MAX_LENGTH: Final = 255
AUTH_ROLE_MAX_LENGTH: Final = 64
AUTH_ROLE_SOURCE_MAX_LENGTH: Final = 32
AUTH_DEFAULT_TENANT: Final = "default"
AUTH_SESSION_TOKEN_BYTES: Final = 32
AUTH_CHALLENGE_TOKEN_BYTES: Final = 32


# Сохраняем str+Enum wire-семантику machine contract.
class AuthSessionStatus(str, Enum):  # noqa: UP042
    """Состояние server-side auth session."""

    ACTIVE = "active"
    REVOKED = "revoked"


# Сохраняем str+Enum wire-семантику machine contract.
class UserRoleStatus(str, Enum):  # noqa: UP042
    """Состояние provider-neutral роли global account."""

    ACTIVE = "active"
    REVOKED = "revoked"


AUTH_RUNTIME_CONSTRAINTS: Final = MappingProxyType(
    {
        "challenge_pk": "pk_auth_challenges",
        "challenge_hash_unique": "uq_auth_challenges_challenge_hash",
        "challenge_provider_format": (
            "ck_auth_challenges_provider_format"
        ),
        "challenge_provider_not_mock": (
            "ck_auth_challenges_provider_not_mock"
        ),
        "challenge_tenant": "ck_auth_challenges_tenant",
        "challenge_purpose": "ck_auth_challenges_purpose",
        "challenge_domain": "ck_auth_challenges_domain",
        "challenge_hash": "ck_auth_challenges_hash",
        "challenge_expiry": "ck_auth_challenges_expiry",
        "challenge_terminal_state": "ck_auth_challenges_terminal_state",
        "session_pk": "pk_auth_sessions",
        "session_global_fk": (
            "fk_auth_sessions_global_id_users_global_id"
        ),
        "identity_session_pair_unique": (
            "uq_user_identities_id_global_id"
        ),
        "session_identity_fk": (
            "fk_auth_sessions_identity_global_user_identities"
        ),
        "session_hash_unique": "uq_auth_sessions_token_hash",
        "session_hash": "ck_auth_sessions_token_hash",
        "session_status": "ck_auth_sessions_status",
        "session_expiry": "ck_auth_sessions_expiry",
        "session_revocation": "ck_auth_sessions_revocation",
        "role_pk": "pk_user_roles",
        "role_global_fk": "fk_user_roles_global_id_users_global_id",
        "role_unique": "uq_user_roles_global_id_role",
        "role_format": "ck_user_roles_role_format",
        "role_source": "ck_user_roles_source",
        "role_status": "ck_user_roles_status",
        "role_revocation": "ck_user_roles_revocation",
    }
)


def build_auth_runtime_storage_contract() -> dict[str, object]:
    """Вернуть machine-readable контракт без raw credentials."""

    return {
        "схема_контракта": "EFHC_AUTH_RUNTIME_STORAGE_V1",
        "цикл": 1613,
        "таблицы": {
            "auth_challenges": {
                "one_time": True,
                "raw_challenge_stored": False,
                "hash": "sha256-hex",
                "atomic_consume": True,
                "expires_at_required": True,
            },
            "auth_sessions": {
                "server_side": True,
                "raw_session_token_stored": False,  # nosec B105
                "hash": "sha256-hex",
                "global_owner": "global_id",
                "physical_fk_target": "efhc_core.users.global_id",
                "identity_fk": "efhc_core.user_identities.id",
            },
            "user_roles": {
                "owner": "global_id",
                "physical_fk_target": "efhc_core.users.global_id",
                "provider_specific_owner": False,
            },
        },
        "side_effects": {
            "account_creation": False,
            "identity_creation": False,
            "auto_merge": False,
            "telegram_switch": False,
            "ton_proof": False,
            "financial_update": False,
        },
    }


__all__ = [
    "AUTH_CHALLENGE_TABLE",
    "AUTH_CHALLENGE_TOKEN_BYTES",
    "AUTH_DEFAULT_TENANT",
    "AUTH_DOMAIN_MAX_LENGTH",
    "AUTH_HASH_HEX_LENGTH",
    "AUTH_PROVIDER_MAX_LENGTH",
    "AUTH_PURPOSE_MAX_LENGTH",
    "AUTH_ROLE_MAX_LENGTH",
    "AUTH_ROLE_SOURCE_MAX_LENGTH",
    "AUTH_RUNTIME_CONSTRAINTS",
    "AUTH_SESSION_TABLE",
    "AUTH_SESSION_TOKEN_BYTES",
    "AUTH_TABLE_SCHEMA",
    "AUTH_TENANT_MAX_LENGTH",
    "AuthSessionStatus",
    "USER_ROLE_TABLE",
    "UserRoleStatus",
    "build_auth_runtime_storage_contract",
]
