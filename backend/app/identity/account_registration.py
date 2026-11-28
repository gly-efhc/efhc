"""Единое транзакционное ядро создания нового аккаунта EFHC.

Цикл 1636 создаёт только общий registration core. Existing-account
resolution, provider identity, wallet binding и migration callers
в профильных сервисах и следующих циклах.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Literal

from app.core.logging_core import get_logger
from app.identity.auth_provider import AuthProvider
from app.identity.reserved_global_ids import is_reserved_global_id_db
from app.identity.types import (
    GlobalId,
    InvalidGlobalId,
    InvalidTelegramId,
    TelegramId,
)
from app.identity.user_identities_storage_contract import (
    USER_IDENTITY_DEFAULT_TENANT,
)
from app.models.identity_models import UserIdentity
from app.models.referral_codes_models import ReferralCode
from app.models.referral_models import ReferralLink
from app.models.user_models import GLOBAL_ID_SEQUENCE, User
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

ReferralRegistrationReason = Literal["attached", "no_code"]

_REF_CODE_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9_-]{4,64}$"
)


class AccountRegistrationError(ValueError):
    """Новый account не создан; внешняя транзакция должна откатиться."""

    code = "account.registration_rejected"
    message = "Новый аккаунт не может быть создан"

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self.message)


@dataclass(frozen=True, slots=True)
class NewAccountRequest:
    """Provider-neutral данные действительно нового аккаунта."""

    provider: AuthProvider
    tg_id: int | None
    referral_start_param: str | None = None
    username: str | None = None


@dataclass(frozen=True, slots=True)
class NewAccountResult:
    """Созданный canonical account без provider-specific identity."""

    global_id: GlobalId
    tg_id: int | None
    referral_attached: bool
    referral_reason: ReferralRegistrationReason


def normalize_referral_start_param(value: str | None) -> str | None:
    """Нормализовать старый Telegram start param без угадывания кода."""

    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.lower().startswith("ref_"):
        raw = raw[4:].strip()
    if not raw or len(raw) > 64:
        return None
    if _REF_CODE_RE.fullmatch(raw) is None:
        return None
    return raw


def _validated_username(value: str | None) -> str | None:
    if value is None:
        return None
    clean = str(value).strip()
    if not clean:
        return None
    if len(clean) > 64:
        raise AccountRegistrationError("USERNAME_TOO_LONG")
    return clean


async def _allocate_regular_global_id(session: AsyncSession) -> int:
    """Получить следующий ``global_id``, пропуская reserved values."""

    while True:
        value = await session.scalar(
            select(GLOBAL_ID_SEQUENCE.next_value())
        )
        if value is None:
            raise AccountRegistrationError("GLOBAL_ID_SEQUENCE_EMPTY")
        numeric = int(value)
        if not is_reserved_global_id_db(numeric):
            return numeric


def _global_id_from_user(user: User) -> GlobalId:
    try:
        return GlobalId.from_database(user.global_id)
    except InvalidGlobalId as exc:
        raise AccountRegistrationError("GLOBAL_ID_MISSING") from exc


async def _lock_referral_owner(
    session: AsyncSession,
    code: str,
) -> GlobalId | None:
    referral_code = await session.scalar(
        select(ReferralCode)
        .where(ReferralCode.code == code)
        .with_for_update()
    )
    if referral_code is None:
        return None
    try:
        inviter_global_id = GlobalId.from_database(
            referral_code.inviter_global_id
        )
    except InvalidGlobalId as exc:
        raise AccountRegistrationError(
            "REFERRAL_OWNER_GLOBAL_ID_INVALID"
        ) from exc
    inviter = await session.scalar(
        select(User)
        .where(User.global_id == inviter_global_id.value)
        .with_for_update()
    )
    if inviter is None or inviter.is_active is not True:
        raise AccountRegistrationError("REFERRAL_OWNER_NOT_AVAILABLE")
    return inviter_global_id


async def resolve_referral_code(
    session: AsyncSession,
    code: str,
) -> int | None:
    """Разрешить referral code в canonical ``global_id``."""
    clean = normalize_referral_start_param(code)
    if clean is None:
        return None
    owner = await _lock_referral_owner(session, clean)
    if owner is None:
        return None
    return int(owner.value)


class AccountRegistrationService:
    """Единственная реализация вставки действительно нового ``User``."""

    async def create_new_account(
        self,
        session: AsyncSession,
        request: NewAccountRequest,
    ) -> NewAccountResult:
        """Создать account и referral link в открытой транзакции."""

        if not isinstance(session, AsyncSession):
            raise AccountRegistrationError("SESSION_INVALID")
        if not session.in_transaction():
            raise AccountRegistrationError("TRANSACTION_REQUIRED")
        if not isinstance(request, NewAccountRequest):
            raise AccountRegistrationError("REQUEST_INVALID")
        if not isinstance(request.provider, AuthProvider):
            raise AccountRegistrationError("PROVIDER_INVALID")

        parsed_tg_id: TelegramId | None = None
        if request.tg_id is not None:
            try:
                parsed_tg_id = TelegramId.from_provider(request.tg_id)
            except InvalidTelegramId as exc:
                raise AccountRegistrationError("TG_ID_INVALID") from exc
        elif request.provider is AuthProvider.TELEGRAM:
            raise AccountRegistrationError("TELEGRAM_TG_ID_REQUIRED")

        raw_referral = str(request.referral_start_param or "").strip()
        referral_owner: GlobalId | None = None
        if raw_referral:
            clean_referral = normalize_referral_start_param(
                request.referral_start_param
            )
            if clean_referral is None:
                raise AccountRegistrationError("invalid_code")
            referral_owner = await _lock_referral_owner(
                session,
                clean_referral,
            )
            if referral_owner is not None and parsed_tg_id is not None:
                inviter_subject = await session.scalar(
                    select(UserIdentity.provider_subject)
                    .where(
                        UserIdentity.global_id == referral_owner.value,
                        UserIdentity.provider == AuthProvider.TELEGRAM.value,
                        UserIdentity.provider_tenant
                        == USER_IDENTITY_DEFAULT_TENANT,
                    )
                    .limit(1)
                )
                if (
                    inviter_subject is not None
                    and inviter_subject == str(parsed_tg_id.value)
                ):
                    raise AccountRegistrationError("self_ref")

        if parsed_tg_id is not None:
            existing = await session.scalar(
                select(UserIdentity.id)
                .where(
                    UserIdentity.provider == AuthProvider.TELEGRAM.value,
                    UserIdentity.provider_tenant
                    == USER_IDENTITY_DEFAULT_TENANT,
                    UserIdentity.provider_subject
                    == str(parsed_tg_id.value),
                )
                .with_for_update()
            )
            if existing is not None:
                raise AccountRegistrationError(
                    "ACCOUNT_ALREADY_EXISTS"
                )

        if raw_referral and referral_owner is None:
            raise AccountRegistrationError("code_not_found")

        allocated_global_id = await _allocate_regular_global_id(session)
        user = User(
            global_id=allocated_global_id,
            username=_validated_username(request.username),
        )
        session.add(user)
        try:
            await session.flush()
        except IntegrityError as exc:
            raise AccountRegistrationError("STORAGE_CONFLICT") from exc

        global_id = _global_id_from_user(user)
        referral_attached = False
        referral_reason: ReferralRegistrationReason = "no_code"

        if referral_owner is not None:
            inviter_global_id = referral_owner
            if inviter_global_id == global_id:
                raise AccountRegistrationError("self_ref")
            session.add(
                ReferralLink(
                    inviter_global_id=inviter_global_id.value,
                    invitee_global_id=global_id.value,
                )
            )
            try:
                await session.flush()
            except IntegrityError as exc:
                raise AccountRegistrationError(
                    "REFERRAL_ATTRIBUTION_CONFLICT"
                ) from exc
            logger.info(
                "referral_link_created inviter_global_id=%s "
                "invitee_global_id=%s",
                inviter_global_id.value,
                global_id.value,
            )
            referral_attached = True
            referral_reason = "attached"

        return NewAccountResult(
            global_id=global_id,
            tg_id=(parsed_tg_id.value if parsed_tg_id else None),
            referral_attached=referral_attached,
            referral_reason=referral_reason,
        )


_DEFAULT_ACCOUNT_REGISTRATION_SERVICE = AccountRegistrationService()


async def create_new_account(
    session: AsyncSession,
    request: NewAccountRequest,
) -> NewAccountResult:
    """Каноническая функция-вход для будущих provider callers."""

    service = _DEFAULT_ACCOUNT_REGISTRATION_SERVICE
    return await service.create_new_account(session, request)


def build_account_registration_contract() -> dict[str, object]:
    """Вернуть машинно-проверяемый контракт ядра цикла 1636."""

    return {
        "cycle": 1636,
        "account_owner": "global_id",
        "transaction_required": True,
        "commits_inside_service": False,
        "creates": ["users", "referral_links"],
        "provider_identity_outside_service": True,
        "caller_migration": "bot_webapp_ton",
        "invalid_referral": "fail_closed",
        "late_referral_binding": "forbidden",
        "ton_referral_supported": True,
        "invitee_provider_attribute_nullable": True,
    }


__all__ = [
    "AccountRegistrationError",
    "AccountRegistrationService",
    "NewAccountRequest",
    "NewAccountResult",
    "ReferralRegistrationReason",
    "build_account_registration_contract",
    "create_new_account",
    "normalize_referral_start_param",
    "resolve_referral_code",
]
