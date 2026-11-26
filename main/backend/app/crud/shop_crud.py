# backend/app/crud/shop_crud.py
# ======================================================================
# Назначение кода:
# CRUD для ShopItem. Основной сервис магазина использует
# SQL-оркестрацию, но этот модуль полезен для админки/сидера.
# ======================================================================

from __future__ import annotations

from app.models.shop_models import ShopItem
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def get_item_by_code(
    db: AsyncSession,
    code: str,
) -> ShopItem | None:
    """Вернуть актив или None по коду товара."""
    stmt = select(ShopItem).where(ShopItem.code == code)
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def list_active_items(
    db: AsyncSession,
    limit: int = 200,
) -> list[ShopItem]:
    """Список активных товаров (is_active=TRUE), лимит сверху."""
    stmt = (
        select(ShopItem)
        .where(ShopItem.is_active.is_(True))
        .order_by(ShopItem.id.asc())
        .limit(limit)
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())
