"""Действующий реестр семантики идентификаторов EFHC.

Реестр описывает post-cutover состояние цикла 1692. Активных
compatibility aliases нет: ``global_id`` является единственным account
и business owner, ``tg_id`` остаётся Telegram provider subject.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final, Literal

from app.identity.reserved_global_ids import SUPERADMIN_GLOBAL_ID_TEXT

IdentitySemantic = Literal[
    "canonical_global_identity",
    "local_record_primary_key",
    "provider_identity",
]
RegistryStatus = Literal["canonical", "local_only", "provider_only"]


CANONICAL_PROVIDER_SUBJECT_FIELDS: Final[dict[str, str]] = {
    "telegram": "tg_id",
    "ton": "ton_wallet_id",
    "google": "google_id",
    "apple": "apple_id",
    "facebook": "fb_id",
    "discord": "discord_id",
    "github": "github_id",
}


@dataclass(frozen=True, slots=True)
class IdentityNamePolicy:
    """Политика одного действующего имени идентификатора."""

    name: str
    semantic: IdentitySemantic
    status: RegistryStatus
    owner_allowed: bool
    wire_type: str
    physical_database_name: str | None
    allowed_scopes: tuple[str, ...]
    forbidden_new_uses: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HistoricalScopePolicy:
    """Путь, где историческая терминология не управляет runtime."""

    path_prefix: str
    purpose: str
    may_define_current_runtime: bool


@dataclass(frozen=True, slots=True)
class IdentityGuardFilePolicy:
    """Файл действующего identity guard."""

    path: str
    max_identifier_occurrences: int
    semantic: str
    reason: str


IDENTITY_NAME_POLICIES: Final[tuple[IdentityNamePolicy, ...]] = (
    IdentityNamePolicy(
        name="global_id",
        semantic="canonical_global_identity",
        status="canonical",
        owner_allowed=True,
        wire_type="string_10_ascii_digits",
        physical_database_name="users.global_id",
        allowed_scopes=(
            "business_owner",
            "internal_api",
            "orm_fk",
            "admin_actor",
            "financial_idempotency",
        ),
        forbidden_new_uses=(
            "derive_from_provider_without_resolution",
            "derive_from_local_pk",
            "javascript_number",
            "json_number",
        ),
    ),
    IdentityNamePolicy(
        name="id",
        semantic="local_record_primary_key",
        status="local_only",
        owner_allowed=False,
        wire_type="table_local",
        physical_database_name=None,
        allowed_scopes=("local_table_primary_key",),
        forbidden_new_uses=(
            "account_owner",
            "cross_subsystem_identity",
            "provider_subject",
        ),
    ),
    IdentityNamePolicy(
        name="tg_id",
        semantic="provider_identity",
        status="provider_only",
        owner_allowed=False,
        wire_type="telegram_safe_integer",
        physical_database_name="user_identities.provider_subject[telegram]",
        allowed_scopes=(
            "telegram_authentication",
            "telegram_ingress",
            "telegram_delivery",
            "provider_identity_mapping",
            "telegram_payment_metadata",
            "historical_provider_read_through",
        ),
        forbidden_new_uses=(
            "business_owner",
            "financial_owner",
            "owner_fk",
            "internal_api_owner",
            "admin_actor_owner",
        ),
    ),
)

IDENTITY_GUARD_FILES: Final[tuple[IdentityGuardFilePolicy, ...]] = (
    IdentityGuardFilePolicy(
        path="ops/identity/check_global_id_canon.py",
        max_identifier_occurrences=200,
        semantic="AUTH_IDENTITY_GUARD",
        reason="Fail-closed проверка current global_id canon.",
    ),
)

HISTORICAL_SCOPES: Final[tuple[HistoricalScopePolicy, ...]] = (
    HistoricalScopePolicy(
        path_prefix="docs/cycles/",
        purpose="Исторические и будущие диапазоны рабочих циклов.",
        may_define_current_runtime=False,
    ),
    HistoricalScopePolicy(
        path_prefix="docs/chats/",
        purpose="Нумерованные полные transcripts проектных чатов.",
        may_define_current_runtime=False,
    ),
    HistoricalScopePolicy(
        path_prefix="reports/numbered/",
        purpose="Immutable numbered reports истории развития проекта.",
        may_define_current_runtime=False,
    ),
)


def get_identity_name_policy(name: str) -> IdentityNamePolicy:
    """Вернуть зарегистрированную семантику имени."""

    for policy in IDENTITY_NAME_POLICIES:
        if policy.name == name:
            return policy
    raise KeyError(f"Имя идентификатора не зарегистрировано: {name}")


def build_identity_registry() -> dict[str, object]:
    """Сформировать JSON-ready реестр действующей identity-модели."""

    return {
        "схема_реестра": "EFHC_IDENTITY_REGISTRY_V2",
        "цикл": 1706,
        "версия": "v173.27",
        "канонический_идентификатор": "global_id",
        "физическая_owner_колонка": "users.global_id",
        "canonical_provider_subject_fields": dict(
            CANONICAL_PROVIDER_SUBJECT_FIELDS
        ),
        "identity_resolution": "provider + subject -> global_id",
        "reserved_global_ids": {
            "superadmin": SUPERADMIN_GLOBAL_ID_TEXT,
        },
        "business_owner_tg_id": 0,
        "active_compatibility_aliases": 0,
        "политики_имён": [
            {
                **asdict(policy),
                "allowed_scopes": list(policy.allowed_scopes),
                "forbidden_new_uses": list(policy.forbidden_new_uses),
            }
            for policy in IDENTITY_NAME_POLICIES
        ],
        "разрешённые_guard_файлы": [
            {
                "путь": policy.path,
                "максимум_упоминаний": policy.max_identifier_occurrences,
                "семантика": policy.semantic,
                "причина": policy.reason,
            }
            for policy in IDENTITY_GUARD_FILES
        ],
        "исторические_области": [
            asdict(policy) for policy in HISTORICAL_SCOPES
        ],
        "historical_read_through_only": True,
        "runtime_read_switch": True,
        "financial_ownership_switch": True,
        "physical_rename_complete": True,
        "legacy_alias_removal_complete": True,
    }


__all__ = [
    "HISTORICAL_SCOPES",
    "IDENTITY_GUARD_FILES",
    "IDENTITY_NAME_POLICIES",
    "HistoricalScopePolicy",
    "IdentityGuardFilePolicy",
    "IdentityNamePolicy",
    "build_identity_registry",
    "get_identity_name_policy",
]
