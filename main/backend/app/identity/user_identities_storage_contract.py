"""Канонический storage-contract таблицы ``user_identities``."""

from __future__ import annotations

from enum import Enum
from types import MappingProxyType
from typing import Final

USER_IDENTITY_PROVIDER_MAX_LENGTH: Final = 32
USER_IDENTITY_TENANT_MAX_LENGTH: Final = 128
USER_IDENTITY_SUBJECT_MAX_LENGTH: Final = 512
USER_IDENTITY_STATUS_MAX_LENGTH: Final = 16
USER_IDENTITY_DEFAULT_TENANT: Final = "default"
USER_IDENTITY_TABLE_SCHEMA: Final = "efhc_core"
USER_IDENTITY_TABLE_NAME: Final = "user_identities"
USER_IDENTITY_GLOBAL_ID_MIN: Final = 1
USER_IDENTITY_GLOBAL_ID_MAX: Final = 9_999_999_999


# Сохраняем историческую str+Enum семантику storage contract.
class UserIdentityStatus(str, Enum):  # noqa: UP042
    """Закрытые storage-состояния внешней идентичности."""

    ACTIVE = "active"
    DISABLED = "disabled"
    REVOKED = "revoked"


USER_IDENTITY_CONSTRAINTS: Final = MappingProxyType(
    {
        "primary_key": "pk_user_identities",
        "foreign_key": (
            "fk_user_identities_global_id_users_global_id"
        ),
        "unique_subject": (
            "uq_user_identities_provider_tenant_subject"
        ),
        "global_id_range": "ck_user_identities_global_id_range",
        "provider_format": "ck_user_identities_provider_format",
        "provider_not_mock": "ck_user_identities_provider_not_mock",
        "tenant_length": "ck_user_identities_tenant_length",
        "subject_length": "ck_user_identities_subject_length",
        "status": "ck_user_identities_status",
        "verified_at": "ck_user_identities_verified_at",
        "primary_state": "ck_user_identities_primary_state",
        "primary_per_global": (
            "uq_user_identities_primary_per_global"
        ),
    }
)


def build_user_identities_storage_contract() -> dict[str, object]:
    """Вернуть machine-readable contract без runtime side effects."""

    return {
        "схема_контракта": "EFHC_PROVIDER_IDENTITY_STORAGE_V2",
        "цикл": 1692,
        "статус": "ACTIVE_RELEASE_SCHEMA",
        "таблица": (
            f"{USER_IDENTITY_TABLE_SCHEMA}."
            f"{USER_IDENTITY_TABLE_NAME}"
        ),
        "назначение": (
            "Связь проверенного provider subject с одним global_id"
        ),
        "колонки": [
            "id",
            "global_id",
            "provider",
            "provider_tenant",
            "provider_subject",
            "status",
            "is_primary",
            "is_verified",
            "verified_at",
            "metadata",
            "created_at",
            "updated_at",
        ],
        "global_id": {
            "тип": "BIGINT",
            "nullable": False,
            "минимум": USER_IDENTITY_GLOBAL_ID_MIN,
            "максимум": USER_IDENTITY_GLOBAL_ID_MAX,
            "логический_owner": True,
            "физический_fk_target": "efhc_core.users.global_id",
        },
        "provider": {
            "тип": "VARCHAR(32)",
            "формат": "^[a-z][a-z0-9_]{0,31}$",
            "mock_разрешён_в_production_storage": False,
            "registry_authoritative": True,
        },
        "provider_tenant": {
            "тип": "VARCHAR(128)",
            "nullable": False,
            "default": USER_IDENTITY_DEFAULT_TENANT,
            "универсальная_нормализация": False,
        },
        "provider_subject": {
            "тип": "VARCHAR(512)",
            "nullable": False,
            "универсальная_нормализация": False,
            # Булев флаг storage-контракта, не secret.
            "raw_secret": False,  # nosec B105
        },
        "status": {
            "тип": "VARCHAR(16)",
            "значения": [item.value for item in UserIdentityStatus],
            "default": UserIdentityStatus.ACTIVE.value,
        },
        "уникальность": {
            "provider_tenant_subject": True,
            "одна_primary_identity_на_global_id": True,
        },
        "verification": {
            "is_verified_согласован_с_verified_at": True,
            "primary_требует_active_verified": True,
        },
        "side_effects": {
            "historical_backfill": False,
            "users_update": False,
            "financial_update": False,
            "runtime_resolver": False,
            "account_creation": False,
            "session_issue": False,
            "auto_merge": False,
        },
        "доказательство": {
            "postgresql_установлен_в_среде_чата": False,
            "postgresql_tests_выполнены": False,
            "канонический_ci_workflow_изменён": False,
        },
    }


__all__ = [
    "USER_IDENTITY_CONSTRAINTS",
    "USER_IDENTITY_DEFAULT_TENANT",
    "USER_IDENTITY_GLOBAL_ID_MAX",
    "USER_IDENTITY_GLOBAL_ID_MIN",
    "USER_IDENTITY_PROVIDER_MAX_LENGTH",
    "USER_IDENTITY_STATUS_MAX_LENGTH",
    "USER_IDENTITY_SUBJECT_MAX_LENGTH",
    "USER_IDENTITY_TABLE_NAME",
    "USER_IDENTITY_TABLE_SCHEMA",
    "USER_IDENTITY_TENANT_MAX_LENGTH",
    "UserIdentityStatus",
    "build_user_identities_storage_contract",
]
