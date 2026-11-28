"""TEST-only prebinding: verified Telegram initData -> existing Neon TEST SuperAdmin.

A mere numeric Telegram ID never authenticates an account. The canonical
Telegram adapter first verifies HMAC signature, timestamp and replay boundary.
This override is registered ONLY by demo_backend.asgi, not the production app.
Owner prebinding is read from efhc_admin.admin_whitelist and never from browser
parameters. No identity is marked verified before signed initData is received.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database_core import get_session_factory
from app.identity.auth_provider import AuthProvider
from app.identity.telegram_init_data import VerifiedTelegramInitData
from app.identity.telegram_auth_session import (
    TELEGRAM_AUTH_SESSION_TTL,
    TelegramAccountResolution,
    TelegramAuthSessionError,
    TelegramAuthSessionResult,
    TelegramAuthSessionService,
    _bind_replay_owner,
    _claim_replay,
    _lock_identity,
    _lock_user_by_global_id,
    _telegram_provider_metadata,
)
from app.identity.types import GlobalId
from app.identity.user_identities_storage_contract import (
    USER_IDENTITY_DEFAULT_TENANT,
    UserIdentityStatus,
)
from app.models.identity_models import UserIdentity


class DemoTelegramOwnerBindingService(TelegramAuthSessionService):
    """Bind only after verification, in the canonical atomic login transaction."""

    async def login_in_transaction(
        self,
        session: AsyncSession,
        verified: VerifiedTelegramInitData,
        *,
        referral_start_param: str | None = None,
    ) -> TelegramAuthSessionResult:
        if not isinstance(verified, VerifiedTelegramInitData):
            raise TelegramAuthSessionError("VERIFICATION_REQUIRED")
        subject = verified.verified_identity.provider_subject
        if (
            verified.verified_identity.provider is not AuthProvider.TELEGRAM
            or subject != str(verified.tg_id.value)
        ):
            raise TelegramAuthSessionError("PROVIDER_SUBJECT_MISMATCH")

        # Only a previously registered *active* TEST SuperAdmin is eligible.
        # A Telegram identifier provided in a form/header cannot reach here.
        bound_global_id = (
            await session.execute(
                text(
                    """
                    SELECT aw.global_id
                    FROM efhc_admin.admin_whitelist AS aw
                    JOIN efhc_admin.admin_role AS ar ON ar.admin_id = aw.id
                    JOIN efhc_core.users AS u ON u.global_id = aw.global_id
                    WHERE aw.tg_id = :tg_id
                      AND aw.is_active = TRUE
                      AND u.is_active = TRUE
                      AND ar.role::text = 'superadmin'
                    FOR UPDATE OF aw
                    """
                ),
                {"tg_id": int(verified.tg_id.value)},
            )
        ).scalar_one_or_none()
        if bound_global_id is None:
            return await super().login_in_transaction(
                session, verified, referral_start_param=referral_start_param
            )

        global_id = GlobalId.from_database(int(bound_global_id))
        existing = await _lock_identity(session, provider_subject=subject)
        if existing is not None:
            if (
                int(existing.global_id) != int(bound_global_id)
                or existing.status != UserIdentityStatus.ACTIVE.value
                or existing.is_verified is not True
                or existing.verified_at is None
            ):
                raise TelegramAuthSessionError("DEMO_OWNER_BINDING_CONFLICT")
            return await super().login_in_transaction(
                session, verified, referral_start_param=referral_start_param
            )

        # The signed Telegram initData has already passed HMAC + freshness.
        # Replay claim, identity binding, account and session share one tx.
        replay_event_id = await _claim_replay(session, verified.replay_key)
        await _lock_user_by_global_id(session, global_id)
        identity = UserIdentity(
            global_id=int(bound_global_id),
            provider=AuthProvider.TELEGRAM.value,
            provider_tenant=USER_IDENTITY_DEFAULT_TENANT,
            provider_subject=subject,
            status=UserIdentityStatus.ACTIVE.value,
            is_primary=True,
            is_verified=True,
            verified_at=verified.verified_at,
            provider_metadata=_telegram_provider_metadata(verified),
        )
        session.add(identity)
        await session.flush()
        await _bind_replay_owner(
            session, event_id=replay_event_id, global_id=global_id
        )
        issued = await self._session_service.issue_in_transaction(
            session,
            global_id=global_id,
            identity_id=int(identity.id),
            ttl=TELEGRAM_AUTH_SESSION_TTL,
        )
        return TelegramAuthSessionResult(
            TelegramAccountResolution(
                global_id=global_id,
                outcome="existing_identity",
                identity_id=int(identity.id),
            ),
            issued,
        )


def get_demo_telegram_owner_binding_service() -> DemoTelegramOwnerBindingService:
    return DemoTelegramOwnerBindingService(get_session_factory())
