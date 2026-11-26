"""PostgreSQL-регрессия единого владельца Shop/payment transaction."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from app import deps
from app.routes import shop_routes
from app.schemas.shop_schemas import ShopOrderExternalIn
from app.services.shop_service import ShopFacade
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def test_external_order_откатывается_если_intent_creation_падает(
    async_engine,
    db_clean,
    integration_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with integration_session_factory() as db:
        global_id = int(
            (
                await db.execute(
                    text(
                        "INSERT INTO efhc_core.users DEFAULT VALUES "
                        "RETURNING global_id"
                    )
                )
            ).scalar_one()
        )
        await db.execute(
            text(
                """
                INSERT INTO efhc_core.shop_items (
                    sku, title, description, quantity_efhc,
                    is_active, extra, created_at, updated_at
                ) VALUES (
                    'tx-owner-pg', 'TX owner', 'integration', 1,
                    TRUE,
                    CAST(:extra AS jsonb), NOW(), NOW()
                )
                """
            ),
            {
                "extra": (
                    '{"item_type":"EFHC_PACKAGE",'
                    '"price_ton":"1.00",'
                    '"pay_currencies":["TON"]}'
                )
            },
        )
        await db.commit()

        async def wallet_ok(*_args, **_kwargs) -> None:
            return None

        async def intent_boom(*_args, **_kwargs):
            raise RuntimeError("intent creation failed")

        monkeypatch.setattr(deps, "require_wallet_connected", wallet_ok)

        async def primary_wallets(*_args, **_kwargs):
            return [
                SimpleNamespace(
                    wallet_address="UQ_TEST_PRIMARY_WALLET",
                    wallet_app="Tonkeeper",
                    is_primary=True,
                    is_active=True,
                    proof_verified=True,
                )
            ]

        monkeypatch.setattr(
            shop_routes.wallets_service,
            "list_wallets",
            primary_wallets,
        )
        monkeypatch.setattr(
            shop_routes,
            "create_intent_shop_external_in_transaction",
            intent_boom,
        )

        with pytest.raises(RuntimeError, match="intent creation failed"):
            await shop_routes.create_order_external(
                SimpleNamespace(state=SimpleNamespace()),
                ShopOrderExternalIn(
                    sku="tx-owner-pg",
                    quantity=1,
                    pay_method="TON",
                ),
                db=db,
                owner=SimpleNamespace(global_id=global_id),
                idempotency_key="shop-uow-pg-001",
                svc=ShopFacade(db),
            )

    async with async_engine.connect() as conn:
        count = int(
            (
                await conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM efhc_core.shop_orders
                        WHERE global_id=:global_id
                          AND idempotency_key='shop-uow-pg-001'
                        """
                    ),
                    {"global_id": global_id},
                )
            ).scalar_one()
        )
    assert count == 0


async def test_crud_savepoint_сохраняет_предыдущую_root_mutation(
    async_engine,
    db_clean,
    integration_session_factory,
) -> None:
    from app.crud.tasks_crud import create_task

    async with integration_session_factory() as db:
        await create_task(
            db,
            {
                "code": "crud-savepoint-pg",
                "title": "Базовая задача",
                "type": "custom",
                "active": True,
                "bonus_efhc": 0,
                "limit_per_user": 1,
                "performed_count": 0,
            },
        )
        await db.commit()

    async with integration_session_factory() as db:
        global_id = int(
            (
                await db.execute(
                    text(
                        "INSERT INTO efhc_core.users (username) "
                        "VALUES ('crud_savepoint_owner') RETURNING global_id"
                    )
                )
            ).scalar_one()
        )
        with pytest.raises(ValueError, match="integrity violation"):
            await create_task(
                db,
                {
                    "code": "crud-savepoint-pg",
                    "title": "Дубликат",
                    "type": "custom",
                    "active": True,
                    "bonus_efhc": 0,
                    "limit_per_user": 1,
                    "performed_count": 0,
                },
            )
        await db.commit()

    async with async_engine.connect() as conn:
        owner_count = int(
            (
                await conn.execute(
                    text(
                        "SELECT COUNT(*) FROM efhc_core.users "
                        "WHERE global_id=:global_id"
                    ),
                    {"global_id": global_id},
                )
            ).scalar_one()
        )
    assert owner_count == 1
