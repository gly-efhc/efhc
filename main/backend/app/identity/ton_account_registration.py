"""Transactional TON account resolution и registration цикла 1617."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from app.identity.account_registration import (
    AccountRegistrationError,
    NewAccountRequest,
    create_new_account,
)
from app.identity.auth_provider import AuthProvider
from app.identity.identity_resolver import PostgreSQLIdentityResolver
from app.identity.resolver_contracts import IdentityResolutionStatus
from app.identity.ton_proof_verification import VerifiedTonProof
from app.identity.types import GlobalId, InvalidGlobalId
from app.identity.user_identities_storage_contract import (
    USER_IDENTITY_DEFAULT_TENANT,
    UserIdentityStatus,
)
from app.models.identity_models import UserIdentity
from app.models.user_models import User
from app.models.wallets_models import WalletBinding
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

TonAccountOutcome = Literal[
    "existing_identity",
    "existing_binding",
    "registered",
]

_PROOF_SOURCE: Final[str] = "ton_login_v1"


class TonAccountRegistrationError(ValueError):
    """TON account flow завершён fail closed без выбора account."""

    code = "auth.ton_account_conflict"
    message = "TON account не может быть разрешён"

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self.message)


@dataclass(frozen=True, slots=True)
class TonAccountRegistration:
    """Результат без session и без provider subject в repr."""

    global_id: GlobalId
    outcome: TonAccountOutcome
    identity_id: int
    binding_id: int

    def __repr__(self) -> str:
        return (
            "TonAccountRegistration("
            "global_id='<redacted>', "
            f"outcome={self.outcome!r}, "
            f"identity_id={self.identity_id!r}, "
            f"binding_id={self.binding_id!r})"
        )


async def _lock_identity(
    session: AsyncSession,
    *,
    provider_subject: str,
) -> UserIdentity | None:
    statement = (
        select(UserIdentity)
        .where(
            UserIdentity.provider == AuthProvider.TON.value,
            UserIdentity.provider_tenant
            == USER_IDENTITY_DEFAULT_TENANT,
            UserIdentity.provider_subject == provider_subject,
        )
        .with_for_update()
    )
    return await session.scalar(statement)


async def _lock_binding(
    session: AsyncSession,
    *,
    provider_subject: str,
) -> WalletBinding | None:
    statement = (
        select(WalletBinding)
        .where(WalletBinding.wallet_address == provider_subject)
        .with_for_update()
    )
    return await session.scalar(statement)


async def _lock_user_by_global_id(
    session: AsyncSession,
    global_id: GlobalId,
) -> User:
    statement = (
        select(User)
        .where(User.global_id == global_id.value)
        .with_for_update()
    )
    user = await session.scalar(statement)
    if user is None:
        raise TonAccountRegistrationError("ACCOUNT_NOT_FOUND")
    if user.is_active is not True:
        raise TonAccountRegistrationError("ACCOUNT_INACTIVE")
    return user


async def _validate_binding_owner(
    binding: WalletBinding,
    expected_global_id: GlobalId,
) -> None:
    """Проверить владельца wallet-binding только по каноническому ``global_id``."""

    if binding.global_id is None:
        raise TonAccountRegistrationError("BINDING_OWNER_MISSING")
    try:
        binding_global_id = GlobalId.from_database(binding.global_id)
    except InvalidGlobalId as exc:
        raise TonAccountRegistrationError(
            "BINDING_GLOBAL_ID_INVALID"
        ) from exc
    if binding_global_id != expected_global_id:
        raise TonAccountRegistrationError("WALLET_IDENTITY_CONFLICT")


async def _has_primary_identity(
    session: AsyncSession,
    global_id: GlobalId,
) -> bool:
    statement = (
        select(UserIdentity.id)
        .where(
            UserIdentity.global_id == global_id.value,
            UserIdentity.is_primary.is_(True),
        )
        .limit(1)
    )
    return await session.scalar(statement) is not None


async def _has_primary_binding(
    session: AsyncSession,
    global_id: GlobalId,
) -> bool:
    statement = (
        select(WalletBinding.id)
        .where(
            WalletBinding.global_id == global_id.value,
            WalletBinding.is_primary.is_(True),
            WalletBinding.is_active.is_(True),
        )
        .limit(1)
    )
    return await session.scalar(statement) is not None


def _registration_error_reason(reason: str) -> str:
    mapping = {
        "invalid_code": "REFERRAL_CODE_INVALID",
        "code_not_found": "REFERRAL_CODE_NOT_FOUND",
        "self_ref": "REFERRAL_SELF",
    }
    return mapping.get(reason, reason)


class TonAccountRegistrationService:
    """Открыть существующий account или создать TON-only account."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        if not isinstance(session_factory, async_sessionmaker):
            raise TonAccountRegistrationError("SERVICE_CONFIG_INVALID")
        self._session_factory = session_factory
        self._identity_resolver = PostgreSQLIdentityResolver(
            session_factory
        )

    async def register_or_resolve(
        self,
        proof: VerifiedTonProof,
        *,
        referral_start_param: str | None = None,
    ) -> TonAccountRegistration:
        """Выполнить account, identity и binding одной транзакцией."""

        if not isinstance(proof, VerifiedTonProof):
            raise TonAccountRegistrationError("PROOF_REQUIRED")
        if (
            proof.verified_identity.provider
            is not AuthProvider.TON
        ):
            raise TonAccountRegistrationError("PROVIDER_INVALID")
        try:
            async with (
                self._session_factory() as session,
                session.begin(),
            ):
                return await self.register_or_resolve_in_transaction(
                    session,
                    proof,
                    referral_start_param=referral_start_param,
                )
        except IntegrityError as exc:
            raise TonAccountRegistrationError(
                "STORAGE_CONFLICT"
            ) from exc

    async def register_or_resolve_in_transaction(
        self,
        session: AsyncSession,
        proof: VerifiedTonProof,
        *,
        referral_start_param: str | None = None,
    ) -> TonAccountRegistration:
        """Выполнить flow внутри уже открытой транзакции."""

        if not isinstance(session, AsyncSession):
            raise TonAccountRegistrationError("SESSION_INVALID")
        if not session.in_transaction():
            raise TonAccountRegistrationError(
                "TRANSACTION_REQUIRED"
            )
        if not isinstance(proof, VerifiedTonProof):
            raise TonAccountRegistrationError("PROOF_REQUIRED")
        if (
            proof.verified_identity.provider
            is not AuthProvider.TON
        ):
            raise TonAccountRegistrationError("PROVIDER_INVALID")

        identity = proof.verified_identity
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
            raise TonAccountRegistrationError(reason)

        if resolution.status is IdentityResolutionStatus.RESOLVED:
            if resolution.global_id is None:
                raise TonAccountRegistrationError(
                    "IDENTITY_RESOLUTION_INVALID"
                )
            return await self._resolve_existing_identity(
                session,
                proof=proof,
                global_id=resolution.global_id,
            )

        return await self._resolve_missing_identity(
            session,
            proof=proof,
            referral_start_param=referral_start_param,
        )

    async def _resolve_existing_identity(
        self,
        session: AsyncSession,
        *,
        proof: VerifiedTonProof,
        global_id: GlobalId,
    ) -> TonAccountRegistration:
        await _lock_user_by_global_id(session, global_id)
        identity = await _lock_identity(
            session,
            provider_subject=proof.ton_wallet_id,
        )
        if identity is None:
            raise TonAccountRegistrationError(
                "IDENTITY_RESOLUTION_DRIFT"
            )
        binding = await _lock_binding(
            session,
            provider_subject=proof.ton_wallet_id,
        )
        if binding is None:
            binding = WalletBinding(
                global_id=global_id.value,
                tg_id=None,
                wallet_address=proof.ton_wallet_id,
                wallet_app=None,
                is_primary=not await _has_primary_binding(
                    session,
                    global_id,
                ),
                is_active=True,
                proof_verified=True,
                proof_verified_at=proof.verified_at,
                proof_payload_hash=None,
                proof_source=_PROOF_SOURCE,
            )
            session.add(binding)
            await session.flush()
        else:
            await _validate_binding_owner(binding, global_id)
            if binding.is_active is not True:
                raise TonAccountRegistrationError(
                    "BINDING_INACTIVE"
                )
            binding.global_id = global_id.value
            binding.proof_verified = True
            binding.proof_verified_at = proof.verified_at
            binding.proof_source = _PROOF_SOURCE
            await session.flush()
        return TonAccountRegistration(
            global_id=global_id,
            outcome="existing_identity",
            identity_id=int(identity.id),
            binding_id=int(binding.id),
        )

    async def _resolve_missing_identity(
        self,
        session: AsyncSession,
        *,
        proof: VerifiedTonProof,
        referral_start_param: str | None,
    ) -> TonAccountRegistration:
        binding = await _lock_binding(
            session,
            provider_subject=proof.ton_wallet_id,
        )
        if binding is not None:
            return await self._bind_existing_wallet(
                session,
                proof=proof,
                binding=binding,
            )

        return await self._register_new_ton_account(
            session,
            proof=proof,
            referral_start_param=referral_start_param,
        )

    async def _bind_existing_wallet(
        self,
        session: AsyncSession,
        *,
        proof: VerifiedTonProof,
        binding: WalletBinding,
    ) -> TonAccountRegistration:
        if binding.is_active is not True:
            raise TonAccountRegistrationError("BINDING_INACTIVE")
        if binding.proof_verified is not True:
            raise TonAccountRegistrationError(
                "BINDING_UNVERIFIED"
            )

        if binding.global_id is None:
            raise TonAccountRegistrationError("BINDING_OWNER_MISSING")
        try:
            global_id = GlobalId.from_database(binding.global_id)
        except InvalidGlobalId as exc:
            raise TonAccountRegistrationError(
                "BINDING_GLOBAL_ID_INVALID"
            ) from exc
        await _lock_user_by_global_id(session, global_id)
        await _validate_binding_owner(binding, global_id)

        is_primary = not await _has_primary_identity(
            session,
            global_id,
        )
        identity = UserIdentity(
            global_id=global_id.value,
            provider=AuthProvider.TON.value,
            provider_tenant=USER_IDENTITY_DEFAULT_TENANT,
            provider_subject=proof.ton_wallet_id,
            status=UserIdentityStatus.ACTIVE.value,
            is_primary=is_primary,
            is_verified=True,
            verified_at=proof.verified_at,
            provider_metadata={
                "network": proof.network,
                "key_source": proof.key_source,
            },
        )
        session.add(identity)
        binding.proof_verified_at = proof.verified_at
        binding.proof_source = _PROOF_SOURCE
        await session.flush()
        return TonAccountRegistration(
            global_id=global_id,
            outcome="existing_binding",
            identity_id=int(identity.id),
            binding_id=int(binding.id),
        )

    async def _register_new_ton_account(
        self,
        session: AsyncSession,
        *,
        proof: VerifiedTonProof,
        referral_start_param: str | None,
    ) -> TonAccountRegistration:
        try:
            registered = await create_new_account(
                session,
                NewAccountRequest(
                    provider=AuthProvider.TON,
                    tg_id=None,
                    referral_start_param=referral_start_param,
                ),
            )
        except AccountRegistrationError as exc:
            raise TonAccountRegistrationError(
                _registration_error_reason(exc.reason)
            ) from exc
        global_id = registered.global_id

        identity = UserIdentity(
            global_id=global_id.value,
            provider=AuthProvider.TON.value,
            provider_tenant=USER_IDENTITY_DEFAULT_TENANT,
            provider_subject=proof.ton_wallet_id,
            status=UserIdentityStatus.ACTIVE.value,
            is_primary=True,
            is_verified=True,
            verified_at=proof.verified_at,
            provider_metadata={
                "network": proof.network,
                "key_source": proof.key_source,
            },
        )
        binding = WalletBinding(
            global_id=global_id.value,
            tg_id=None,
            wallet_address=proof.ton_wallet_id,
            wallet_app=None,
            is_primary=True,
            is_active=True,
            proof_verified=True,
            proof_verified_at=proof.verified_at,
            proof_payload_hash=None,
            proof_source=_PROOF_SOURCE,
        )
        session.add_all([identity, binding])
        await session.flush()
        if registered.tg_id is not None:
            raise TonAccountRegistrationError(
                "FAKE_TG_ID_FORBIDDEN"
            )
        return TonAccountRegistration(
            global_id=global_id,
            outcome="registered",
            identity_id=int(identity.id),
            binding_id=int(binding.id),
        )


def build_ton_account_registration_contract() -> dict[str, object]:
    """Сформировать machine contract цикла 1617."""

    return {
        "схема": "EFHC_TON_ACCOUNT_REGISTRATION_V1",
        "цикл": 1617,
        "provider": AuthProvider.TON.value,
        "provider_subject_field": "ton_wallet_id",
        "provider_subject_semantics": "TON wallet address",
        "результаты": [
            "existing_identity",
            "existing_binding",
            "registered",
        ],
        "атомарность": {
            "account_identity_binding": True,
            "advisory_lock_by_identity": True,
            "one_wallet_one_global_account": True,
        },
        "ton_only": {
            "provider_identity_in_user_identities": True,
            "fake_tg_id": False,
            "global_id_generated_by_sequence": True,
        },
        "fail_closed": {
            "auto_merge": False,
            "unverified_binding": True,
            "inactive_binding": True,
            "conflicting_owner": True,
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
        "side_effects": {
            "session_issue": False,
            "financial_update": False,
            "read_switch": False,
        },
        "alembic_head": "0001",
    }


__all__ = [
    "TonAccountOutcome",
    "TonAccountRegistration",
    "TonAccountRegistrationError",
    "TonAccountRegistrationService",
    "build_ton_account_registration_contract",
]
