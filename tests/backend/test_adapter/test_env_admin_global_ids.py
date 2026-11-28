"""ENV Global ID TEST Admin policy and original RBAC isolation.

The real TEST service additionally verifies the current Neon guest lease in
middleware; these unit tests intentionally use a fake DB dependency.
"""
from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.deps import require_admin_or_nft_or_key, require_admin_write
from app.services.admin.admin_rbac import RBAC, AdminRole, AdminAuthError
from demo_backend.config import DemoConfig, DemoConfigurationError, parse_test_admin_ids
from demo_backend.env_admin import authorized_test_admin, install_admin_role_compatibility
from demo_backend.preview_access import install_preview_admin
from demo_backend.session_store import DemoSessionStore


def test_list_is_strict_and_never_accepts_owner_88_or_unknown_id():
    assert parse_test_admin_ids("0000003101, 0000003257") == frozenset({
        "0000003101", "0000003257",
    })
    assert not parse_test_admin_ids("")
    for raw in ("0000000088", "3101", "0000004001",
                "0000003101,", "0000003101,0000003101",
                "0000003101;0000003257", "0000000000"):
        with pytest.raises(DemoConfigurationError):
            parse_test_admin_ids(raw)


def config() -> DemoConfig:
    return DemoConfig(
        database_url="postgresql://test:pass@localhost/neondb?sslmode=require",
        neon_host="localhost", password="operator-test-password-123456",
        initial_global_id="0000001000", cors_origins=("https://test.example",),
        cookie_secure=False, cookie_name="efhc_demo_sid",
        scheduler_enabled=False, scheduler_period=60,
        max_topup_efhc="10000.00000000", dataset="genesis",
        admin_global_ids=frozenset({"0000003101"}),
    )


@contextmanager
def patched_rbac(cfg):
    funcs = ["resolve_admin", "admin_from_auth_context", "require_role", "is_superadmin"]
    old = {key: RBAC.__dict__[key] for key in funcs}
    try:
        install_admin_role_compatibility(cfg)
        yield
    finally:
        for key, value in old.items():
            setattr(RBAC, key, value)


@pytest.mark.asyncio
async def test_full_test_admin_access_requires_exact_server_attested_owner():
    cfg = config()
    sessions = DemoSessionStore()
    owner = sessions.issue("0000003101", scope="guest", lease_hash="a" * 64)
    stranger = sessions.issue("0000003257", scope="guest", lease_hash="b" * 64)

    async def fake_db():
        yield object()

    from app.core.database_core import fastapi_db_dependency
    app = FastAPI()
    app.dependency_overrides[fastapi_db_dependency] = fake_db
    install_preview_admin(app, sessions, cfg)

    @app.get("/api/admin/access")
    async def admin_read(auth=Depends(require_admin_or_nft_or_key)):
        return {"gid": auth.global_id, "role": auth.role}

    @app.post("/api/admin/write")
    async def admin_write(auth=Depends(require_admin_write)):
        return {"gid": auth.global_id, "role": auth.role}

    def headers(session):
        return {"Authorization": f"Bearer {session.token}"}

    with (
        patched_rbac(cfg),
        patch("demo_backend.preview_access.is_safe_synthetic_account",
              new_callable=AsyncMock, return_value=True),
        patch("demo_backend.preview_access.test_admin_lease_active",
              new_callable=AsyncMock, return_value=True),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # A valid token for a different global ID is never an Admin.
            assert (await client.get(
                "/api/admin/access", headers=headers(stranger)
            )).status_code == 403
            # A forged raw ID does not create an Admin context.
            assert (await client.get("/api/admin/access")).status_code == 403
            assert (await client.get(
                "/api/admin/access", headers=headers(owner)
            )).status_code == 403
            with authorized_test_admin(3101):
                read = await client.get("/api/admin/access", headers=headers(owner))
                write = await client.post("/api/admin/write", headers=headers(owner))
                assert read.status_code == 200, read.text
                assert write.status_code == 200, write.text
                assert read.json()["gid"] == 3101
                assert write.json()["role"] == AdminRole.SUPERADMIN
                admin = RBAC.admin_from_auth_context(SimpleNamespace(
                    global_id=3101, admin_id=0, role=AdminRole.SUPERADMIN,
                    auth_source="env_global_id_test_guest_lease",
                ))
                RBAC.require_role(admin, AdminRole.SUPERADMIN)
                assert RBAC.is_superadmin(admin)
            with pytest.raises(AdminAuthError):
                RBAC.require_role(admin, AdminRole.MODERATOR)
