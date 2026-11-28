"""TEST-only authenticated Global ID Admin gate (no public preview bypass).

Render's EFHC_TEST_ADMIN_GLOBAL_IDS is the list of permitted IDs, never an
identity proof. The exact server-issued session AND live matching guest lease
are required for each Admin route, including write dependencies.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database_core import fastapi_db_dependency
from app.deps import AuthContext, require_admin_or_nft_or_key
from app.services.admin.admin_rbac import AdminRole
from demo_backend.account_guards import is_safe_synthetic_account
from demo_backend.config import DemoConfig
from demo_backend.env_admin import current_test_admin
from demo_backend.session_store import DemoSessionStore


async def test_admin_lease_active(
    db: AsyncSession, global_id: str, digest: str | None,
    *, allow_reserved_quarantine: bool = False,
) -> bool:
    """An exact, unexpired lease is mandatory for every scope.

    Quarantine controls *new guest allocation* and unsafe TEST reset.
    An ENV-reserved Admin with their existing matching lease remains usable.
    The caller may set the exception ONLY after server-side ENV/scope checks.
    """
    if not digest:
        return False
    row = (await db.execute(text("""
        SELECT EXISTS(
            SELECT 1 FROM efhc_test.guest_leases l
            WHERE l.global_id=:gid AND l.token_hash=:digest
              AND l.expires_at > now()
              AND (CAST(:allow_reserved_quarantine AS boolean) OR NOT EXISTS(
                SELECT 1 FROM efhc_test.guest_slot_quarantine q
                WHERE q.global_id=l.global_id
              ))
        )
    """), {
        "gid": int(global_id), "digest": digest,
        "allow_reserved_quarantine": allow_reserved_quarantine,
    })).scalar_one()
    return bool(row)


def install_preview_admin(app, sessions: DemoSessionStore, config: DemoConfig) -> None:
    """Install on isolated demo ASGI app; production deps remain untouched."""

    async def test_admin(
        request: Request,
        db: AsyncSession = Depends(fastapi_db_dependency),
    ) -> AuthContext:
        header = request.headers.get("authorization", "")
        bearer = header[7:] if header.startswith("Bearer ") else ""
        session = sessions.get(bearer)
        if session is None or session.scope not in {"guest", "operator"}:
            raise HTTPException(status_code=403, detail="TEST_ADMIN_SESSION_REQUIRED")
        if (
            not config.genesis_mode
            or session.global_id not in config.admin_global_ids
            or current_test_admin() != int(session.global_id)
        ):
            raise HTTPException(status_code=403, detail="TEST_ADMIN_GLOBAL_ID_NOT_ALLOWED")
        if not await is_safe_synthetic_account(db, session.global_id):
            raise HTTPException(status_code=403, detail="TEST_ADMIN_IDENTITY_INVALID")
        if not await test_admin_lease_active(
            db, session.global_id, session.lease_hash,
            allow_reserved_quarantine=True,
        ):
            raise HTTPException(status_code=403, detail="TEST_ADMIN_LEASE_INVALID")
        request.state.efhc_test_admin_global_id = int(session.global_id)
        return AuthContext(
            global_id=int(session.global_id),
            admin_id=0,
            role=AdminRole.SUPERADMIN,
            is_admin=True,
            auth_source="env_global_id_test_guest_lease",
        )

    app.dependency_overrides[require_admin_or_nft_or_key] = test_admin
