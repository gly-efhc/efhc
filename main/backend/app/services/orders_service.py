"""Read-only доступ к historical/internal строкам ShopOrder.

Все активные записи магазина принадлежат canonical shop/browser-shop
сервисам. Этот модуль намеренно не предоставляет write-path для платежей,
остатков или NFT.
"""

from __future__ import annotations

from app.models.shop_models import ShopOrder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def get_order(
    session: AsyncSession,
    *,
    order_id: int,
) -> ShopOrder | None:
    """Вернуть один заказ по primary key."""
    return await session.get(ShopOrder, int(order_id))


async def list_user_orders(
    session: AsyncSession,
    *,
    global_id: int,
    limit: int = 50,
) -> list[ShopOrder]:
    """Вернуть последние заказы canonical account owner."""
    result = await session.execute(
        select(ShopOrder)
        .where(ShopOrder.global_id == int(global_id))
        .order_by(ShopOrder.order_id.desc())
        .limit(int(limit))
    )
    return list(result.scalars().all())


__all__ = ["get_order", "list_user_orders"]
