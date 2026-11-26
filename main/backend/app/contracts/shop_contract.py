# backend/app/contracts/shop_contract.py

from __future__ import annotations

from typing import Protocol

from app.schemas.shop_schemas import (
    ShopOrderExternalIn,
    ShopOrderExternalOut,
    ShopPurchaseByEFHCIn,
    ShopPurchaseByEFHCOut,
)


class ShopContract(Protocol):
    async def get_catalog(self, owner_id: int) -> list[dict]:
        """Каталог Shop для canonical owner."""

    async def create_external_order_in_transaction(
        self,
        global_id: int,
        payload: ShopOrderExternalIn,
        client_nonce: str | None,
    ) -> ShopOrderExternalOut:
        """Создать внешний заказ без root commit/rollback."""

    async def create_external_order(
        self,
        global_id: int,
        payload: ShopOrderExternalIn,
        client_nonce: str | None,
    ) -> ShopOrderExternalOut:
        """Создать внешний заказ TON/USDT по ``global_id``."""

    async def purchase_by_efhc(
        self,
        global_id: int,
        payload: ShopPurchaseByEFHCIn,
        idempotency_key: str,
    ) -> ShopPurchaseByEFHCOut:
        """Внутренняя покупка EFHC по ``global_id``."""

    async def list_orders_by_owner(
        self,
        global_id: int,
        limit: int,
        cursor: str | None,
    ) -> dict:
        """Список заказов единого аккаунта."""
