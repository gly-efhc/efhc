"""Transactional Telegram account/session flow цикла 1619."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Final, Literal

from app.identity.account_registration import (
    AccountRegistrationError,
    NewAccountRequest,
    create_new_account,
)
from app.identity.auth_errors import (
    AuthSessionNotActive,
    InvalidAuthRuntimeInput,
)
from app.identity.auth_provider import AuthProvider
from app.identity.auth_runtime_services import (
    AuthSessionService,
    IssuedAuthSession,
)
from app.identity.identity_resolver import PostgreSQLIdentityResolver
from app.identity.resolver_contracts import IdentityResolutionStatus
from app.identity.telegram_init_data import VerifiedTelegramInitData
from app.identity.types import GlobalId, InvalidGlobalId
from app.identity.user_identities_storage_contract import (
    USER_IDENTITY_DEFAULT_TENANT,
    UserIdentityStatus,
)
from app.models.external_events_models import ProcessedExternalEvent
from app.models.identity_models import UserIdentity
from app.models.user_models import User
from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

TelegramAccountOutcome = Literal[
    "existing_identity",
    "registered",
]

TELEGRAM_AUTH_SESSION_TTL: Final[timedelta] = timedelta(days=30)
_REPLAY_PROVIDER: Final[str] = "telegram_init_data_auth"


def _telegram_provider_metadata(
    verified: VerifiedTelegramInitData,
    existing: object | None = None,
) -> dict[str, object]:
    metadata = dict(existing) if isinstance(existing, dict) else {}
    metadata.update({
        "source": "telegram_webapp_init_data",
        "auth_date": int(verified.auth_date.timestamp()),
    })
    if verified.profile_photo_url:
        metadata["avatar_url"] = verified.profile_photo_url
    return metadata


class TelegramAuthSessionError(ValueError):
    """Telegram account/session flow завершён fail closed."""

    code = "auth.telegram_session_failed"
    message = "Telegram auth session не может быть выдана"

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self.message)


@dataclass(frozen=True, slots=True)
class TelegramAccountResolution:
    """Account result без provider subject в repr."""

    global_id: GlobalId
    outcome: TelegramAccountOutcome
    identity_id: int

    def __repr__(self) -> str:
        return (
            "TelegramAccountResolution("
            "global_id='<redacted>', "
            f"outcome={self.outcome!r}, "
            f"identity_id={self.identity_id!r})"
        )


@dataclass(frozen=True, slots=True)
class TelegramAuthSessionResult:
    """Атомарный результат account resolution и session issue."""

    account: TelegramAccountResolution
    session: IssuedAuthSession

    def __repr__(self) -> str:
        return (
            "TelegramAuthSessionResult("
            f"account={self.account!r}, "
            "session='<redacted>')"
        )


async def _lock_user_by_global_id(
    session: AsyncSession,
    global_id: GlobalId,
) -> User:
    user = await session.scalar(
        select(User)
        .where(User.global_id == global_id.value)
        .with_for_update()
    )
    if user is None:
        raise TelegramAuthSessionError("ACCOUNT_NOT_FOUND")
    if user.is_active is not True:
        raise TelegramAuthSessionError("ACCOUNT_INACTIVE")
    return user


async def _lock_identity(
    session: AsyncSession,
    *,
    provider_subject: str,
) -> UserIdentity | None:
    return await session.scalar(
        select(UserIdentity)
        .where(
            UserIdentity.provider == AuthProvider.TELEGRAM.value,
            UserIdentity.provider_tenant
            == USER_IDENTITY_DEFAULT_TENANT,
            UserIdentity.provider_subject == provider_subject,
        )
        .with_for_update()
    )


async def _claim_replay(
    session: AsyncSession,
    replay_key: str,
) -> int:
    statement = (
        postgresql_insert(ProcessedExternalEvent)
        .values(
            provider=_REPLAY_PROVIDER,
            event_id=replay_key,
        )
        .on_conflict_do_nothing(
            constraint=(
                "uq_processed_external_events_provider_event_id"
            )
        )
        .returning(ProcessedExternalEvent.id)
    )
    claimed = (await session.execute(statement)).scalar_one_or_none()
    if claimed is None:
        raise TelegramAuthSessionError("INIT_DATA_REPLAY")
    return int(claimed)


async def _bind_replay_owner(
    session: AsyncSession,
    *,
    event_id: int,
    global_id: GlobalId,
) -> None:
    """Сохранить owner без изменения replay/security semantics."""

    statement = (
        update(ProcessedExternalEvent)
        .where(
            ProcessedExternalEvent.id == int(event_id),
            or_(
                ProcessedExternalEvent.resolved_global_id.is_(None),
                ProcessedExternalEvent.resolved_global_id
                == global_id.value,
            ),
        )
        .values(resolved_global_id=global_id.value)
        .returning(ProcessedExternalEvent.id)
    )
    bound = (await session.execute(statement)).scalar_one_or_none()
    if bound is None:
        raise TelegramAuthSessionError("INIT_DATA_OWNER_CONFLICT")


def _registration_error_reason(reason: str) -> str:
    mapping = {
        "invalid_code": "REFERRAL_CODE_INVALID",
        "code_not_found": "REFERRAL_CODE_NOT_FOUND",
        "self_ref": "REFERRAL_SELF",
    }
    return mapping.get(reason, reason)


async def resolve_telegram_subject_global_id(
    session: AsyncSession,
    telegram_subject_id: int,
) -> GlobalId | None:
    """Разрешить проверенную Telegram identity в canonical GlobalId.

    Provider subject используется только на Telegram boundary. Функция
    не назначает привилегии и не выполняет business-операции.
    """

    rows = list(
        (
            await session.scalars(
                select(UserIdentity.global_id)
                .where(
                    UserIdentity.provider
                    == AuthProvider.TELEGRAM.value,
                    UserIdentity.provider_tenant
                    == USER_IDENTITY_DEFAULT_TENANT,
                    UserIdentity.provider_subject
                    == str(int(telegram_subject_id)),
                    UserIdentity.status == "active",
                    UserIdentity.is_verified.is_(True),
                    UserIdentity.verified_at.is_not(None),
                )
                .order_by(UserIdentity.id)
                .limit(2)
            )
        ).all()
    )
    if len(rows) != 1:
        return None
    try:
        return GlobalId.from_database(rows[0])
    except InvalidGlobalId:
        return None


class TelegramAuthSessionService:
    """Разрешить Telegram identity и выдать session атомарно."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        if not isinstance(session_factory, async_sessionmaker):
            raise TelegramAuthSessionError("SERVICE_CONFIG_INVALID")
        self._session_factory = session_factory
        self._identity_resolver = PostgreSQLIdentityResolver(
            session_factory
        )
        self._session_service = AuthSessionService(session_factory)

    async def login(
        self,
        verified: VerifiedTelegramInitData,
        *,
        referral_start_param: str | None = None,
    ) -> TelegramAuthSessionResult:
        """Открыть собственную транзакцию Telegram login."""

        if not isinstance(verified, VerifiedTelegramInitData):
            raise TelegramAuthSessionError("VERIFICATION_REQUIRED")
        try:
            async with (
                self._session_factory() as session,
                session.begin(),
            ):
                return await self.login_in_transaction(
                    session,
                    verified,
                    referral_start_param=referral_start_param,
                )
        except TelegramAuthSessionError:
            raise
        except IntegrityError as exc:
            raise TelegramAuthSessionError(
                "STORAGE_CONFLICT"
            ) from exc
        except (
            AuthSessionNotActive,
            InvalidAuthRuntimeInput,
        ) as exc:
            raise TelegramAuthSessionError(
                "SESSION_ISSUE_DENIED"
            ) from exc

    async def login_in_transaction(
        self,
        session: AsyncSession,
        verified: VerifiedTelegramInitData,
        *,
        referral_start_param: str | None = None,
    ) -> TelegramAuthSessionResult:
        """Выполнить Telegram login во внешней транзакции."""

        if not isinstance(session, AsyncSession):
            raise TelegramAuthSessionError("SESSION_INVALID")
        if not session.in_transaction():
            raise TelegramAuthSessionError(
                "TRANSACTION_REQUIRED"
            )
        if not isinstance(verified, VerifiedTelegramInitData):
            raise TelegramAuthSessionError("VERIFICATION_REQUIRED")
        identity = verified.verified_identity
        if identity.provider is not AuthProvider.TELEGRAM:
            raise TelegramAuthSessionError("PROVIDER_INVALID")

        replay_event_id = await _claim_replay(
            session,
            verified.replay_key,
        )
        resolution = await (
            self._identity_resolver.resolve_in_transaction(
                session,
                identity,
            )
        )
        if resolution.status is IdentityResolutionStatus.CONFLICT:
            reason = "IDENTITY_CONFLICT"
            if resolution.conflict_code is not None:
                reason = (
                    "IDENTITY_"
                    + resolution.conflict_code.value.upper()
                )
            raise TelegramAuthSessionError(reason)

        if resolution.status is IdentityResolutionStatus.RESOLVED:
            if resolution.global_id is None:
                raise TelegramAuthSessionError(
                    "IDENTITY_RESOLUTION_INVALID"
                )
            account = await self._resolve_existing_identity(
                session,
                verified=verified,
                global_id=resolution.global_id,
            )
        else:
            account = await self._resolve_missing_identity(
                session,
                verified=verified,
                referral_start_param=referral_start_param,
            )

        await _bind_replay_owner(
            session,
            event_id=replay_event_id,
            global_id=account.global_id,
        )
        issued = await self._session_service.issue_in_transaction(
            session,
            global_id=account.global_id,
            identity_id=account.identity_id,
            ttl=TELEGRAM_AUTH_SESSION_TTL,
        )
        return TelegramAuthSessionResult(account, issued)

    async def _resolve_existing_identity(
        self,
        session: AsyncSession,
        *,
        verified: VerifiedTelegramInitData,
        global_id: GlobalId,
    ) -> TelegramAccountResolution:
        await _lock_user_by_global_id(session, global_id)
        identity = await _lock_identity(
            session,
            provider_subject=(
                verified.verified_identity.provider_subject
            ),
        )
        if identity is None:
            raise TelegramAuthSessionError(
                "IDENTITY_RESOLUTION_DRIFT"
            )
        if identity.global_id != global_id.value:
            raise TelegramAuthSessionError("IDENTITY_CONFLICT")
        identity.provider_metadata = _telegram_provider_metadata(
            verified, identity.provider_metadata
        )
        identity.verified_at = verified.verified_at
        return TelegramAccountResolution(
            global_id=global_id,
            outcome="existing_identity",
            identity_id=int(identity.id),
        )

    async def _resolve_missing_identity(
        self,
        session: AsyncSession,
        *,
        verified: VerifiedTelegramInitData,
        referral_start_param: str | None,
    ) -> TelegramAccountResolution:
        """Создать account только при отсутствии provider identity.

        Post-migration runtime не использует ``users.tg_id`` как owner
        fallback. Конфликтующая provider row завершается fail closed через
        uniqueness-контракт регистрации account.
        """

        try:
            registered = await create_new_account(
                session,
                NewAccountRequest(
                    provider=AuthProvider.TELEGRAM,
                    tg_id=verified.tg_id.value,
                    referral_start_param=referral_start_param,
                ),
            )
        except AccountRegistrationError as exc:
            raise TelegramAuthSessionError(
                _registration_error_reason(exc.reason)
            ) from exc

        identity = UserIdentity(
            global_id=registered.global_id.value,
            provider=AuthProvider.TELEGRAM.value,
            provider_tenant=USER_IDENTITY_DEFAULT_TENANT,
            provider_subject=verified.verified_identity.provider_subject,
            status=UserIdentityStatus.ACTIVE.value,
            is_primary=True,
            is_verified=True,
            verified_at=verified.verified_at,
            provider_metadata=_telegram_provider_metadata(verified),
        )
        session.add(identity)
        await session.flush()
        return TelegramAccountResolution(
            global_id=registered.global_id,
            outcome="registered",
            identity_id=int(identity.id),
        )


def build_telegram_auth_session_contract() -> dict[str, object]:
    """Сформировать machine contract цикла 1619."""

    return {
        "схема": "EFHC_TELEGRAM_AUTH_SESSION_V1",
        "цикл": 1619,
        "provider": AuthProvider.TELEGRAM.value,
        "результаты": [
            "existing_identity",
            "registered",
        ],
        "атомарность": {
            "replay_identity_account_session": True,
            "identity_resolver_used": True,
            "one_tg_id_one_global_account": True,
        },
        "session": {
            "server_side": True,
            "raw_token_stored": False,  # nosec B105
            "token_returned_once": True,  # nosec B105
            "ttl_seconds": int(
                TELEGRAM_AUTH_SESSION_TTL.total_seconds()
            ),
        },
        "registration_center": {
            "cycle": 1639,
            "service": "AccountRegistrationService",
            "direct_user_insert": False,
        },
        "referral_transport": {
            "cycle": 1638,
            "normalized_param_accepted": True,
            "existing_account_ignored": True,
            "new_account_consumer": "AccountRegistrationService",
            "loss_before_consumer": False,
        },
        "replay": {
            "storage": "processed_external_events",
            "raw_init_data_stored": False,
            "namespaced_hash_only": True,
        },
        "запреты": {
            "tg_id_as_owner": True,
            "global_id_from_tg_id": True,
            "auto_merge": True,
            "financial_update": True,
            "migration_0006": True,
            "frontend_auth_switch": True,
        },
    }


__all__ = [
    "TELEGRAM_AUTH_SESSION_TTL",
    "TelegramAccountOutcome",
    "TelegramAccountResolution",
    "TelegramAuthSessionError",
    "TelegramAuthSessionResult",
    "TelegramAuthSessionService",
    "build_telegram_auth_session_contract",
]
