from __future__ import annotations

# ruff: noqa: E402,I001

from types import SimpleNamespace

import pytest
from fastapi import FastAPI

httpx = pytest.importorskip("httpx")
sqlalchemy = pytest.importorskip("sqlalchemy")
text = sqlalchemy.text

from app.routes import admin_withdrawals_routes  # noqa: E402

pytestmark = pytest.mark.asyncio


async def _insert_user(db, *, global_id: int) -> None:
    await db.execute(
        text(
            """
            INSERT INTO efhc_core.users (
                global_id, username, is_vip, is_active,
                main_balance, bonus_balance,
                total_generated_kwh, exchanged_kwh_total,
                created_at, updated_at
            ) VALUES (
                :global_id, :username, false, true,
                '100.00000000', '0.00000000',
                '0.00000000', '0.00000000',
                NOW(), NOW()
            )
            """
        ),
        {
            "global_id": global_id,
            "username": f"user_{global_id}",
        },
    )
    await db.commit()


async def _insert_withdraw(db, *, global_id: int) -> int:
    result = await db.execute(
        text(
            """
            INSERT INTO efhc_core.withdraw_requests (
                global_id, amount, status, idempotency_key,
                hold_done, refund_done, external_address,
                created_at, updated_at
            ) VALUES (
                :global_id, '4.00000000', 'PENDING', :idk,
                false, false, :external_address,
                NOW(), NOW()
            )
            RETURNING id
            """
        ),
        {
            "global_id": global_id,
            "idk": f"wd-route-list-{global_id}",
            "external_address": (
                "UQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAJKZ"
            ),
        },
    )
    await db.commit()
    return int(result.scalar_one())


def _app(db_session, *, admin: bool) -> FastAPI:
    app = FastAPI()
    app.include_router(admin_withdrawals_routes.router)

    async def override_get_db():
        yield db_session

    app.dependency_overrides[
        admin_withdrawals_routes.get_db
    ] = override_get_db
    if admin:
        async def override_admin():
            return SimpleNamespace(
                global_id=5_900_000_001,
                admin_id=1,
                role="SuperAdmin",
                is_admin=True,
            )

        app.dependency_overrides[
            admin_withdrawals_routes.require_admin
        ] = override_admin
    return app


async def test_get_admin_withdrawals_returns_real_rows(db_session):
    global_id = 5_232_010_001
    await _insert_user(
        db_session, global_id=global_id
    )
    wid = await _insert_withdraw(
        db_session, global_id=global_id
    )
    app = _app(db_session, admin=True)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get("/admin/withdrawals")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    expected_id = str(wid)
    assert any(row["id"] == expected_id for row in payload)
    row = next(row for row in payload if row["id"] == expected_id)
    assert row["global_id"] == f"{global_id:010d}"
    assert row["status"] == "PENDING"


async def test_get_admin_withdrawals_requires_admin(db_session):
    app = _app(db_session, admin=False)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get("/admin/withdrawals")

    assert response.status_code in {401, 403}
