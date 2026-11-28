"""Isolated TEST Global ID Admin authorization compatibility (never production).

A Global ID is an allowlist identifier, NOT authentication.
Eligibility also requires this request's live, exact hashed Genesis guest lease,
an active synthetic account, and the server-authenticated DEMO session.
"""
from __future__ import annotations

from contextvars import ContextVar
from contextlib import contextmanager
from typing import Iterator

from demo_backend.config import DemoConfig

_active_test_admin: ContextVar[int | None] = ContextVar("efhc_test_admin_actor", default=None)


@contextmanager
def authorized_test_admin(global_id: int) -> Iterator[None]:
    token = _active_test_admin.set(int(global_id))
    try:
        yield
    finally:
        _active_test_admin.reset(token)


def current_test_admin() -> int | None:
    return _active_test_admin.get()


def install_admin_role_compatibility(config: DemoConfig) -> None:
    """Patch only the DEMO process's imported RBAC facade.

    Production app and persisted whitelist/RBAC tables stay untouched. Calls
    outside the verified request context always use the original RBAC rules.
    """
    from app.services.admin.admin_rbac import RBAC, AdminRole, AdminUser, AdminAuthError

    original_resolve = RBAC.resolve_admin
    original_context = RBAC.admin_from_auth_context
    original_require = RBAC.require_role
    original_superadmin = RBAC.is_superadmin

    def allowed_actor(global_id: int) -> bool:
        return (
            config.genesis_mode and f"{int(global_id):010d}" in config.admin_global_ids
            and current_test_admin() == int(global_id)
        )

    async def resolve_admin(db, global_id: int):
        if allowed_actor(global_id):
            return AdminUser(
                id=0, global_id=int(global_id), role=AdminRole.SUPERADMIN,
                is_active=True, tg_id=None,
            )
        return await original_resolve(db, global_id)

    def admin_from_auth_context(auth):
        try:
            gid = int(auth.global_id)
            role = str(auth.role)
            source = str(auth.auth_source)
        except (AttributeError, TypeError, ValueError):
            return original_context(auth)
        if (allowed_actor(gid) and role == AdminRole.SUPERADMIN
                and source == "env_global_id_test_guest_lease"):
            return AdminUser(
                id=0, global_id=gid, role=AdminRole.SUPERADMIN,
                is_active=True, tg_id=None,
            )
        return original_context(auth)

    def require_role(admin, minimal):
        if (allowed_actor(int(admin.global_id))
                and admin.role == AdminRole.SUPERADMIN
                and bool(admin.is_active)):
            required = RBAC._normalize_role(minimal)
            if RBAC._level(required) <= RBAC._level(AdminRole.SUPERADMIN):
                return None
            raise AdminAuthError("TEST_ADMIN_ROLE_INSUFFICIENT")
        return original_require(admin, minimal)

    def is_superadmin(admin):
        return (
            allowed_actor(int(admin.global_id))
            and admin.role == AdminRole.SUPERADMIN and bool(admin.is_active)
        ) or original_superadmin(admin)

    RBAC.resolve_admin = staticmethod(resolve_admin)
    RBAC.admin_from_auth_context = staticmethod(admin_from_auth_context)
    RBAC.require_role = staticmethod(require_role)
    RBAC.is_superadmin = staticmethod(is_superadmin)
