"""Provider-neutral access boundary для Telegram admin entry commands."""

from __future__ import annotations

from app.identity.telegram_auth_session import (
    resolve_telegram_subject_global_id,
)
from app.services.admin.admin_rbac import RBAC, AdminAuthError
from sqlalchemy.ext.asyncio import AsyncSession


async def telegram_sender_has_admin_access(
    db: AsyncSession,
    telegram_subject_id: int,
) -> bool:
    """Разрешить Telegram subject в global_id и проверить server-side RBAC."""

    global_id = await resolve_telegram_subject_global_id(
        db,
        telegram_subject_id,
    )
    if global_id is None:
        return False
    # Telegram bot commands are a separate entrypoint from HTTP. Only the
    # exact signed Telegram owner associated with public Global ID 88 can
    # obtain SuperAdmin privileges; an additional linked Telegram identity
    # on the same account is never implicitly delegated admin rights.
    if global_id.to_database() != 88:
        return False
    try:
        admin = await RBAC.resolve_admin(db, global_id.to_database())
    except AdminAuthError:
        return False
    return admin.role == "SuperAdmin" and admin.tg_id == telegram_subject_id


__all__ = ["telegram_sender_has_admin_access"]
