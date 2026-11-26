"""Transactional PostgreSQL IdentityResolver цикла 1612."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

from app.identity.auth_errors import InvalidIdentityResolution
from app.identity.auth_provider import AuthProvider
from app.identity.resolver_contracts import (
    IdentityConflictCode,
    IdentityResolution,
)
from app.identity.types import GlobalId, InvalidGlobalId
from app.identity.user_identities_storage_contract import (
    USER_IDENTITY_DEFAULT_TENANT,
    USER_IDENTITY_SUBJECT_MAX_LENGTH,
    USER_IDENTITY_TENANT_MAX_LENGTH,
    UserIdentityStatus,
)
from app.identity.verified_identity import VerifiedIdentity
from app.models.identity_models import UserIdentity
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)

_LOCK_NAMESPACE = b"efhc.identity-resolver.v1\x00"


@dataclass(frozen=True, slots=True)
class IdentityResolverCandidate:
    """Минимальный снимок строки без provider subject."""

    global_id: object
    status: object
    is_verified: object
    verified_at_present: bool


def _identity_advisory_lock_key(
    *,
    provider: AuthProvider,
    provider_tenant: str,
    provider_subject: str,
) -> int:
    """Построить стабильный signed BIGINT без раскрытия subject."""

    payload = b"\x1f".join(
        (
            _LOCK_NAMESPACE,
            provider.value.encode("ascii"),
            provider_tenant.encode("utf-8"),
            provider_subject.encode("utf-8"),
        )
    )
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


def _classify_candidates(
    candidates: Sequence[IdentityResolverCandidate],
) -> IdentityResolution:
    """Классифицировать locked storage snapshot fail closed."""

    if not candidates:
        return IdentityResolution.not_found()
    if len(candidates) != 1:
        return IdentityResolution.conflict(
            IdentityConflictCode.MULTIPLE_MATCHES
        )

    candidate = candidates[0]
    if candidate.status != UserIdentityStatus.ACTIVE.value:
        return IdentityResolution.conflict(
            IdentityConflictCode.IDENTITY_INACTIVE
        )
    if (
        candidate.is_verified is not True
        or not candidate.verified_at_present
    ):
        return IdentityResolution.conflict(
            IdentityConflictCode.IDENTITY_UNVERIFIED
        )
    try:
        global_id = GlobalId.from_database(candidate.global_id)
    except InvalidGlobalId:
        return IdentityResolution.conflict(
            IdentityConflictCode.INVALID_GLOBAL_ID
        )
    return IdentityResolution.resolved(global_id)


class PostgreSQLIdentityResolver:
    """Сериализовать lookup и вернуть один fail-closed outcome.

    Public lookup открывает собственную транзакцию. Для будущих
    атомарных auth flows доступен ``resolve_in_transaction``: вызывающий
    код обязан передать уже начатую транзакцию. Resolver не создаёт
    account, identity, session и не выполняет auto-merge.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        provider_tenant: str = USER_IDENTITY_DEFAULT_TENANT,
    ) -> None:
        if not isinstance(session_factory, async_sessionmaker):
            raise InvalidIdentityResolution()
        if (
            not isinstance(provider_tenant, str)
            or not provider_tenant
            or provider_tenant != provider_tenant.strip()
            or len(provider_tenant) > USER_IDENTITY_TENANT_MAX_LENGTH
        ):
            raise InvalidIdentityResolution()
        self._session_factory = session_factory
        self._provider_tenant = provider_tenant

    @property
    def provider_tenant(self) -> str:
        """Вернуть точный tenant lookup без provider subject."""

        return self._provider_tenant

    async def resolve_verified_identity(
        self,
        identity: VerifiedIdentity,
    ) -> IdentityResolution:
        """Выполнить lookup в собственной PostgreSQL-транзакции."""

        async with (
            self._session_factory() as session,
            session.begin(),
        ):
            return await self.resolve_in_transaction(
                session,
                identity,
            )

    async def resolve_in_transaction(
        self,
        session: AsyncSession,
        identity: VerifiedIdentity,
    ) -> IdentityResolution:
        """Выполнить lookup внутри уже открытой транзакции."""

        if not isinstance(session, AsyncSession):
            raise InvalidIdentityResolution()
        if not session.in_transaction():
            raise InvalidIdentityResolution()
        if not isinstance(identity, VerifiedIdentity):
            raise InvalidIdentityResolution()
        if identity.provider is AuthProvider.MOCK:
            return IdentityResolution.conflict(
                IdentityConflictCode.PROVIDER_NOT_STORABLE
            )
        if len(identity.provider_subject) > (
            USER_IDENTITY_SUBJECT_MAX_LENGTH
        ):
            return IdentityResolution.conflict(
                IdentityConflictCode.SUBJECT_NOT_STORABLE
            )

        lock_key = _identity_advisory_lock_key(
            provider=identity.provider,
            provider_tenant=self._provider_tenant,
            provider_subject=identity.provider_subject,
        )
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": lock_key},
        )

        statement = (
            select(UserIdentity)
            .where(
                UserIdentity.provider == identity.provider.value,
                UserIdentity.provider_tenant
                == self._provider_tenant,
                UserIdentity.provider_subject
                == identity.provider_subject,
            )
            .order_by(UserIdentity.id)
            .limit(2)
            .with_for_update()
        )
        rows = list((await session.scalars(statement)).all())
        candidates = tuple(
            IdentityResolverCandidate(
                global_id=row.global_id,
                status=row.status,
                is_verified=row.is_verified,
                verified_at_present=row.verified_at is not None,
            )
            for row in rows
        )
        return _classify_candidates(candidates)


def build_identity_resolver_contract() -> dict[str, object]:
    """Вернуть machine-readable contract цикла 1612."""

    return {
        "схема": "EFHC_TRANSACTIONAL_IDENTITY_RESOLVER_V1",
        "цикл": 1612,
        "вход": "VerifiedIdentity",
        "выходы": [
            "resolved",
            "not_found",
            "conflict",
        ],
        "блокировки": {
            "missing_row": "pg_advisory_xact_lock",
            "existing_row": "SELECT_FOR_UPDATE",
            "ключ_детерминирован": True,
            "ключ_не_содержит_raw_subject": True,
        },
        "транзакция": {
            "public_method_owns_transaction": True,
            "existing_transaction_supported": True,
            "commit_inside_existing_transaction": False,
        },
        "fail_closed": {
            "multiple_matches": True,
            "inactive_identity": True,
            "unverified_identity": True,
            "invalid_global_id": True,
            "mock_provider_storage": True,
            "oversized_subject": True,
        },
        "side_effects": {
            "account_creation": False,
            "identity_creation": False,
            "session_issue": False,
            "auto_merge": False,
            "financial_update": False,
        },
        "hardening_1702": {
            "identity_key": [
                "provider",
                "provider_tenant",
                "provider_subject",
            ],
            "one_pair_one_global_id": True,
            "same_subject_different_provider_distinct": True,
            "collision_fail_closed": True,
            "automatic_account_merge": False,
            "session_owner": "global_id",
            "session_identity_owner_match_required": True,
        },
        "физическая_owner_reference": "users.global_id",
        "логический_owner": "global_id",
    }


__all__ = [
    "IdentityResolverCandidate",
    "PostgreSQLIdentityResolver",
    "build_identity_resolver_contract",
]
