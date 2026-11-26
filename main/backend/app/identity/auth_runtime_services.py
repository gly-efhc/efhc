"""Транзакционные auth-core services цикла 1613."""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, cast

from app.identity.auth_context import AuthContext
from app.identity.auth_errors import (
    AuthChallengeNotConsumable,
    AuthChallengeRateLimited,
    AuthProviderError,
    AuthSessionNotActive,
    InvalidAuthRuntimeInput,
)
from app.identity.auth_provider import AuthProvider
from app.identity.auth_runtime_storage_contract import (
    AUTH_CHALLENGE_TOKEN_BYTES,
    AUTH_DEFAULT_TENANT,
    AUTH_DOMAIN_MAX_LENGTH,
    AUTH_PURPOSE_MAX_LENGTH,
    AUTH_ROLE_MAX_LENGTH,
    AUTH_ROLE_SOURCE_MAX_LENGTH,
    AUTH_SESSION_TOKEN_BYTES,
    AUTH_TENANT_MAX_LENGTH,
    AuthSessionStatus,
    UserRoleStatus,
)
from app.identity.types import GlobalId, InvalidGlobalId
from app.identity.user_identities_storage_contract import (
    UserIdentityStatus,
)
from app.identity.verified_identity import (
    _restore_verified_identity_from_storage,
)
from app.lib.time import utcnow
from app.models.auth_models import AuthChallenge, AuthSession, UserRole
from app.models.identity_models import UserIdentity
from app.models.user_models import User
from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9_-]{32,128}$"
)
_PURPOSE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[a-z][a-z0-9_.:-]{0,63}$"
)
_ROLE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[a-z][a-z0-9_.:-]{0,63}$"
)
_SOURCE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[a-z][a-z0-9_.:-]{0,31}$"
)
_CHALLENGE_HASH_NAMESPACE = b"efhc.auth-challenge.v1\x00"
_SESSION_HASH_NAMESPACE = b"efhc.auth-session.v1\x00"
_MAX_CHALLENGE_TTL = timedelta(hours=1)
_MAX_SESSION_TTL = timedelta(days=90)


def _utc_now() -> datetime:
    return cast(datetime, utcnow())


def _hash_opaque_token(token: object, *, namespace: bytes) -> str:
    """Хешировать строгий high-entropy opaque token."""

    if not isinstance(token, str) or not token.isascii():
        raise InvalidAuthRuntimeInput()
    if _TOKEN_PATTERN.fullmatch(token) is None:
        raise InvalidAuthRuntimeInput()
    return hashlib.sha256(namespace + token.encode("ascii")).hexdigest()


def hash_auth_challenge(token: object) -> str:
    """Получить storage hash challenge без его логирования."""

    return _hash_opaque_token(
        token,
        namespace=_CHALLENGE_HASH_NAMESPACE,
    )


def hash_auth_session_token(token: object) -> str:
    """Получить storage hash session token без его логирования."""

    return _hash_opaque_token(
        token,
        namespace=_SESSION_HASH_NAMESPACE,
    )


def _validate_tenant(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > AUTH_TENANT_MAX_LENGTH
    ):
        raise InvalidAuthRuntimeInput()
    return value


def _validate_domain(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > AUTH_DOMAIN_MAX_LENGTH
        or any(ord(character) < 33 for character in value)
    ):
        raise InvalidAuthRuntimeInput()
    return value


def _validate_purpose(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) > AUTH_PURPOSE_MAX_LENGTH
        or _PURPOSE_PATTERN.fullmatch(value) is None
    ):
        raise InvalidAuthRuntimeInput()
    return value


def validate_auth_role(value: object) -> str:
    """Проверить каноническое provider-neutral имя роли."""

    if (
        not isinstance(value, str)
        or len(value) > AUTH_ROLE_MAX_LENGTH
        or _ROLE_PATTERN.fullmatch(value) is None
    ):
        raise InvalidAuthRuntimeInput()
    return value


def _validate_source(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) > AUTH_ROLE_SOURCE_MAX_LENGTH
        or _SOURCE_PATTERN.fullmatch(value) is None
    ):
        raise InvalidAuthRuntimeInput()
    return value


def _validate_ttl(value: object, *, maximum: timedelta) -> timedelta:
    if not isinstance(value, timedelta):
        raise InvalidAuthRuntimeInput()
    if value <= timedelta(0) or value > maximum:
        raise InvalidAuthRuntimeInput()
    return value


@dataclass(frozen=True, slots=True)
class IssuedAuthChallenge:
    """Challenge credential, который возвращается ровно один раз."""

    challenge_id: uuid.UUID
    token: str
    expires_at: datetime

    def __repr__(self) -> str:
        return (
            "IssuedAuthChallenge("
            f"challenge_id={self.challenge_id!r}, "
            "token='<redacted>', "
            f"expires_at={self.expires_at!r})"
        )


@dataclass(frozen=True, slots=True)
class ConsumedAuthChallenge:
    """Безопасное подтверждение атомарного consumption."""

    challenge_id: uuid.UUID
    provider: AuthProvider
    purpose: str
    domain: str


@dataclass(frozen=True, slots=True)
class IssuedAuthSession:
    """Session credential, raw token не сохраняется в БД."""

    session_id: uuid.UUID
    token: str
    expires_at: datetime

    def __repr__(self) -> str:
        return (
            "IssuedAuthSession("
            f"session_id={self.session_id!r}, "
            "token='<redacted>', "
            f"expires_at={self.expires_at!r})"
        )


class AuthChallengeService:
    """Выдать и атомарно потребить one-time challenge."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        clock: Callable[[], datetime] = _utc_now,
        issuance_fingerprint: str | None = None,
        rate_limit_window_sec: int = 60,
        rate_limit_max_requests: int = 10,
        max_outstanding: int = 5000,
        cleanup_batch: int = 256,
    ) -> None:
        if not isinstance(session_factory, async_sessionmaker):
            raise InvalidAuthRuntimeInput()
        if issuance_fingerprint is not None:
            value = str(issuance_fingerprint).strip().lower()
            if not re.fullmatch(r"[0-9a-f]{64}", value):
                raise InvalidAuthRuntimeInput()
            self._issuance_fingerprint: str | None = value
        else:
            self._issuance_fingerprint = None
        numeric_limits = (
            rate_limit_window_sec,
            rate_limit_max_requests,
            max_outstanding,
            cleanup_batch,
        )
        if any(
            isinstance(value, bool) or int(value) <= 0
            for value in numeric_limits
        ):
            raise InvalidAuthRuntimeInput()
        self._session_factory = session_factory
        self._clock = clock
        self._rate_limit_window_sec = int(rate_limit_window_sec)
        self._rate_limit_max_requests = int(rate_limit_max_requests)
        self._max_outstanding = int(max_outstanding)
        self._cleanup_batch = int(cleanup_batch)

    async def issue(
        self,
        *,
        provider: AuthProvider,
        purpose: str,
        domain: str,
        ttl: timedelta,
        provider_tenant: str = AUTH_DEFAULT_TENANT,
    ) -> IssuedAuthChallenge:
        if not isinstance(provider, AuthProvider):
            raise InvalidAuthRuntimeInput()
        if provider is AuthProvider.MOCK:
            raise InvalidAuthRuntimeInput()
        tenant = _validate_tenant(provider_tenant)
        purpose_value = _validate_purpose(purpose)
        domain_value = _validate_domain(domain)
        ttl_value = _validate_ttl(ttl, maximum=_MAX_CHALLENGE_TTL)
        token = secrets.token_urlsafe(AUTH_CHALLENGE_TOKEN_BYTES)
        now = self._clock()
        expires_at = now + ttl_value
        metadata: dict[str, str] = {}
        if self._issuance_fingerprint is not None:
            metadata["issuance_fingerprint"] = self._issuance_fingerprint
        row = AuthChallenge(
            id=uuid.uuid4(),
            provider=provider.value,
            provider_tenant=tenant,
            purpose=purpose_value,
            domain=domain_value,
            challenge_hash=hash_auth_challenge(token),
            expires_at=expires_at,
            challenge_metadata=metadata,
            created_at=now,
        )
        rate_limited = False
        async with self._session_factory() as session, session.begin():
            # Все выдачи данного provider/purpose сериализуются перед
            # проверкой квот, чтобы конкурентные запросы не обходили предел.
            lock_key = f"auth_challenge:{provider.value}:{purpose_value}"
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": lock_key},
            )

            stale_ids = (
                select(AuthChallenge.id)
                .where(
                    or_(
                        AuthChallenge.expires_at <= now,
                        AuthChallenge.consumed_at.is_not(None),
                        AuthChallenge.invalidated_at.is_not(None),
                    )
                )
                .order_by(AuthChallenge.expires_at.asc())
                .limit(self._cleanup_batch)
            )
            await session.execute(
                delete(AuthChallenge).where(AuthChallenge.id.in_(stale_ids))
            )

            active_count = int(
                (
                    await session.scalar(
                        select(func.count())
                        .select_from(AuthChallenge)
                        .where(
                            AuthChallenge.provider == provider.value,
                            AuthChallenge.purpose == purpose_value,
                            AuthChallenge.consumed_at.is_(None),
                            AuthChallenge.invalidated_at.is_(None),
                            AuthChallenge.expires_at > now,
                        )
                    )
                )
                or 0
            )
            rate_limited = active_count >= self._max_outstanding

            if not rate_limited and self._issuance_fingerprint is not None:
                window_start = now - timedelta(
                    seconds=self._rate_limit_window_sec
                )
                recent_count = int(
                    (
                        await session.scalar(
                            select(func.count())
                            .select_from(AuthChallenge)
                            .where(
                                AuthChallenge.provider == provider.value,
                                AuthChallenge.purpose == purpose_value,
                                AuthChallenge.created_at >= window_start,
                                AuthChallenge.challenge_metadata[
                                    "issuance_fingerprint"
                                ].as_string()
                                == self._issuance_fingerprint,
                            )
                        )
                    )
                    or 0
                )
                rate_limited = (
                    recent_count >= self._rate_limit_max_requests
                )

            if not rate_limited:
                session.add(row)

        if rate_limited:
            raise AuthChallengeRateLimited()
        return IssuedAuthChallenge(row.id, token, expires_at)

    async def consume(
        self,
        token: object,
        *,
        provider: AuthProvider,
        purpose: str,
        domain: str,
        provider_tenant: str = AUTH_DEFAULT_TENANT,
        expected_challenge_id: uuid.UUID | None = None,
    ) -> ConsumedAuthChallenge:
        if not isinstance(provider, AuthProvider):
            raise InvalidAuthRuntimeInput()
        if provider is AuthProvider.MOCK:
            raise InvalidAuthRuntimeInput()
        tenant = _validate_tenant(provider_tenant)
        purpose_value = _validate_purpose(purpose)
        domain_value = _validate_domain(domain)
        token_hash = hash_auth_challenge(token)
        if expected_challenge_id is not None and not isinstance(
            expected_challenge_id,
            uuid.UUID,
        ):
            raise InvalidAuthRuntimeInput()
        now = self._clock()

        predicates = [
            AuthChallenge.challenge_hash == token_hash,
            AuthChallenge.provider == provider.value,
            AuthChallenge.provider_tenant == tenant,
            AuthChallenge.purpose == purpose_value,
            AuthChallenge.domain == domain_value,
            AuthChallenge.consumed_at.is_(None),
            AuthChallenge.invalidated_at.is_(None),
            AuthChallenge.expires_at > now,
        ]
        if expected_challenge_id is not None:
            predicates.append(AuthChallenge.id == expected_challenge_id)

        statement = (
            update(AuthChallenge)
            .where(*predicates)
            .values(consumed_at=now)
            .returning(AuthChallenge.id)
        )
        async with self._session_factory() as session, session.begin():
            challenge_id = (
                await session.execute(statement)
            ).scalar_one_or_none()
        if challenge_id is None:
            raise AuthChallengeNotConsumable()
        return ConsumedAuthChallenge(
            challenge_id=challenge_id,
            provider=provider,
            purpose=purpose_value,
            domain=domain_value,
        )


class UserRoleService:
    """Управлять provider-neutral ролями только по global_id."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if not isinstance(session_factory, async_sessionmaker):
            raise InvalidAuthRuntimeInput()
        self._session_factory = session_factory
        self._clock = clock

    async def list_active(self, global_id: GlobalId) -> frozenset[str]:
        if not isinstance(global_id, GlobalId):
            raise InvalidAuthRuntimeInput()
        async with self._session_factory() as session:
            roles = (
                await session.execute(
                    select(UserRole.role).where(
                        UserRole.global_id == global_id.value,
                        UserRole.status == UserRoleStatus.ACTIVE.value,
                    )
                )
            ).scalars()
            return frozenset(str(role) for role in roles)

    async def grant(
        self,
        global_id: GlobalId,
        role: str,
        *,
        source: str = "system",
    ) -> None:
        if not isinstance(global_id, GlobalId):
            raise InvalidAuthRuntimeInput()
        role_value = validate_auth_role(role)
        source_value = _validate_source(source)
        now = self._clock()
        statement = (
            postgresql_insert(UserRole)
            .values(
                global_id=global_id.value,
                role=role_value,
                source=source_value,
                status=UserRoleStatus.ACTIVE.value,
                granted_at=now,
                revoked_at=None,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_user_roles_global_id_role",
                set_={
                    "source": source_value,
                    "status": UserRoleStatus.ACTIVE.value,
                    "granted_at": now,
                    "revoked_at": None,
                    "updated_at": now,
                },
            )
        )
        async with self._session_factory() as session, session.begin():
            await session.execute(statement)

    async def revoke(self, global_id: GlobalId, role: str) -> bool:
        if not isinstance(global_id, GlobalId):
            raise InvalidAuthRuntimeInput()
        role_value = validate_auth_role(role)
        now = self._clock()
        statement = (
            update(UserRole)
            .where(
                UserRole.global_id == global_id.value,
                UserRole.role == role_value,
                UserRole.status == UserRoleStatus.ACTIVE.value,
            )
            .values(
                status=UserRoleStatus.REVOKED.value,
                revoked_at=now,
                updated_at=now,
            )
            .returning(UserRole.id)
        )
        async with self._session_factory() as session, session.begin():
            return (
                await session.execute(statement)
            ).scalar_one_or_none() is not None


class AuthSessionService:
    """Выдать, проверить и отозвать hashed server-side session."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if not isinstance(session_factory, async_sessionmaker):
            raise InvalidAuthRuntimeInput()
        self._session_factory = session_factory
        self._clock = clock

    async def issue(
        self,
        *,
        global_id: GlobalId,
        identity_id: int,
        ttl: timedelta,
    ) -> IssuedAuthSession:
        """Выдать session в собственной транзакции."""

        async with self._session_factory() as session, session.begin():
            return await self.issue_in_transaction(
                session,
                global_id=global_id,
                identity_id=identity_id,
                ttl=ttl,
            )

    async def issue_in_transaction(
        self,
        session: AsyncSession,
        *,
        global_id: GlobalId,
        identity_id: int,
        ttl: timedelta,
    ) -> IssuedAuthSession:
        """Выдать session внутри уже открытой транзакции."""

        if not isinstance(session, AsyncSession):
            raise InvalidAuthRuntimeInput()
        if not session.in_transaction():
            raise InvalidAuthRuntimeInput()
        if not isinstance(global_id, GlobalId):
            raise InvalidAuthRuntimeInput()
        if (
            isinstance(identity_id, bool)
            or not isinstance(identity_id, int)
        ):
            raise InvalidAuthRuntimeInput()
        if identity_id <= 0:
            raise InvalidAuthRuntimeInput()
        ttl_value = _validate_ttl(ttl, maximum=_MAX_SESSION_TTL)
        now = self._clock()
        expires_at = now + ttl_value
        token = secrets.token_urlsafe(AUTH_SESSION_TOKEN_BYTES)
        session_id = uuid.uuid4()

        identity = (
            await session.execute(
                select(UserIdentity)
                .join(User, User.global_id == UserIdentity.global_id)
                .where(
                    UserIdentity.id == identity_id,
                    UserIdentity.global_id == global_id.value,
                    UserIdentity.status
                    == UserIdentityStatus.ACTIVE.value,
                    UserIdentity.is_verified.is_(True),
                    UserIdentity.verified_at.is_not(None),
                    User.is_active.is_(True),
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if identity is None:
            raise AuthSessionNotActive()
        try:
            provider = AuthProvider.from_wire(identity.provider)
            _restore_verified_identity_from_storage(
                provider,
                identity.provider_subject,
            )
        except AuthProviderError as exc:
            raise AuthSessionNotActive() from exc
        session.add(
            AuthSession(
                id=session_id,
                global_id=global_id.value,
                identity_id=identity_id,
                token_hash=hash_auth_session_token(token),
                status=AuthSessionStatus.ACTIVE.value,
                expires_at=expires_at,
                created_at=now,
                updated_at=now,
            )
        )
        await session.flush()
        return IssuedAuthSession(session_id, token, expires_at)

    async def authenticate(self, token: object) -> AuthContext:
        token_hash = hash_auth_session_token(token)
        now = self._clock()
        async with self._session_factory() as session, session.begin():
            row = (
                await session.execute(
                    select(AuthSession, UserIdentity)
                    .join(
                        UserIdentity,
                        (UserIdentity.id == AuthSession.identity_id)
                        & (
                            UserIdentity.global_id
                            == AuthSession.global_id
                        ),
                    )
                    .join(User, User.global_id == AuthSession.global_id)
                    .where(
                        AuthSession.token_hash == token_hash,
                        AuthSession.status
                        == AuthSessionStatus.ACTIVE.value,
                        AuthSession.revoked_at.is_(None),
                        AuthSession.expires_at > now,
                        UserIdentity.status
                        == UserIdentityStatus.ACTIVE.value,
                        UserIdentity.is_verified.is_(True),
                        UserIdentity.verified_at.is_not(None),
                        User.is_active.is_(True),
                    )
                )
            ).one_or_none()
            if row is None:
                raise AuthSessionNotActive()
            stored_session, identity = row
            stored_session.last_seen_at = now
            stored_session.updated_at = now
            try:
                global_id = GlobalId.from_database(
                    stored_session.global_id
                )
                provider = AuthProvider.from_wire(identity.provider)
                verified_identity = (
                    _restore_verified_identity_from_storage(
                        provider,
                        identity.provider_subject,
                    )
                )
            except (AuthProviderError, InvalidGlobalId) as exc:
                raise AuthSessionNotActive() from exc
            roles = frozenset(
                str(role)
                for role in (
                    await session.execute(
                        select(UserRole.role).where(
                            UserRole.global_id == global_id.value,
                            UserRole.status
                            == UserRoleStatus.ACTIVE.value,
                        )
                    )
                ).scalars()
            )

        return AuthContext(
            global_id=global_id,
            verified_identity=verified_identity,
            roles=roles,
            session_id=str(stored_session.id),
        )

    async def revoke(self, token: object) -> bool:
        token_hash = hash_auth_session_token(token)
        now = self._clock()
        statement = (
            update(AuthSession)
            .where(
                AuthSession.token_hash == token_hash,
                AuthSession.status == AuthSessionStatus.ACTIVE.value,
            )
            .values(
                status=AuthSessionStatus.REVOKED.value,
                revoked_at=now,
                updated_at=now,
            )
            .returning(AuthSession.id)
        )
        async with self._session_factory() as session, session.begin():
            return (
                await session.execute(statement)
            ).scalar_one_or_none() is not None


def build_auth_runtime_services_contract() -> dict[str, object]:
    """Сформировать machine contract services цикла 1613."""

    return {
        "схема": "EFHC_AUTH_RUNTIME_SERVICES_V1",
        "цикл": 1613,
        "challenge": {
            "one_time": True,
            "atomic_consume": True,
            "raw_value_in_storage": False,
            "caller_metadata_accepted": False,
            "issuance_rate_limited": True,
            "outstanding_quota": True,
            "bounded_terminal_cleanup": True,
        },
        "session": {
            "server_side": True,
            "hashed_token": True,  # nosec B105
            "raw_value_in_storage": False,
            "revocable": True,
            "last_seen_updated": True,
            "active_account_required": True,
        },
        "roles": {
            "owner": "global_id",
            "provider_specific": False,
            "concurrent_grant": "postgresql_upsert",
        },
        "dependencies": {
            "missing_credentials": 401,
            "malformed_or_inactive_session": 401,
            "missing_role": 403,
        },
        "запреты": {
            "account_creation": True,
            "identity_creation": True,
            "auto_merge": True,
            "public_auth_endpoint": True,
            "telegram_switch": True,
            "ton_proof": True,
            "financial_update": True,
        },
    }


__all__ = [
    "AuthChallengeService",
    "AuthSessionService",
    "ConsumedAuthChallenge",
    "IssuedAuthChallenge",
    "IssuedAuthSession",
    "UserRoleService",
    "build_auth_runtime_services_contract",
    "hash_auth_challenge",
    "hash_auth_session_token",
    "validate_auth_role",
]
