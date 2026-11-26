"""Admin-фасад единого Shop Management поверх canonical shop_service."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

import app.services.shop_service as _shop
from sqlalchemy.ext.asyncio import AsyncSession


async def admin_list_orders(
    db: AsyncSession,
    *,
    limit: int = 50,
    cursor: str | None = None,
    status: str | None = None,
    item_type: str | None = None,
    global_id: int | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        await _shop.admin_list_orders(
            db,
            limit=int(limit),
            cursor=cursor,
            status=status,
            item_type=item_type,
            global_id=global_id,
        ),
    )


async def admin_list_items(
    db: AsyncSession,
) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], await _shop.admin_list_items(db))


async def admin_upsert_item(
    db: AsyncSession,
    *,
    code: str,
    title: str,
    description: str | None = None,
    item_type: str = "EFHC_PACKAGE",
    quantity_efhc: Decimal | None = None,
    image_url: str | None = None,
    status: str = "draft",
    price_efhc: Decimal | None = None,
    price_ton: Decimal | None = None,
    price_usdt: Decimal | None = None,
    pay_currencies: list[str] | None = None,
    category: str | None = None,
    badge: str | None = None,
    action_mode: str = "checkout",
    external_url: str | None = None,
    delivery_mode: str | None = None,
    sort_order: int = 0,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        await _shop.admin_upsert_item(
            db,
            code=code,
            title=title,
            description=description,
            item_type=item_type,
            quantity_efhc=quantity_efhc,
            image_url=image_url,
            status=status,
            price_efhc=price_efhc,
            price_ton=price_ton,
            price_usdt=price_usdt,
            pay_currencies=pay_currencies,
            category=category,
            badge=badge,
            action_mode=action_mode,
            external_url=external_url,
            delivery_mode=delivery_mode,
            sort_order=int(sort_order),
        ),
    )


async def admin_set_price(
    db: AsyncSession,
    *,
    code: str,
    price_efhc: Decimal | None = None,
    price_ton: Decimal | None = None,
    price_usdt: Decimal | None = None,
    pay_currencies: list[str] | None = None,
    is_active: bool | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        await _shop.admin_set_price(
            db,
            code=code,
            price_efhc=price_efhc,
            price_ton=price_ton,
            price_usdt=price_usdt,
            pay_currencies=pay_currencies,
            is_active=is_active,
        ),
    )


async def admin_set_item_status(
    db: AsyncSession,
    *,
    code: str,
    status: str,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        await _shop.admin_set_item_status(
            db,
            code=code,
            status=status,
        ),
    )


async def admin_delete_item(
    db: AsyncSession,
    *,
    code: str,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        await _shop.admin_delete_item(
            db,
            code=code,
        ),
    )


async def admin_order_status_counters(
    db: AsyncSession,
) -> dict[str, Any]:
    """Вернуть глобальные счётчики Shop orders для Admin dashboard."""
    return cast(
        dict[str, Any],
        await _shop.admin_order_status_counters(db),
    )


async def admin_force_fulfill_order(
    db: AsyncSession,
    *,
    order_id: int,
    reason: str | None = None,
    actor_global_id: int | None = None,
    admin_id: int | None = None,
    admin_role: str | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        await _shop.admin_force_fulfill_order(
            db,
            order_id=int(order_id),
            reason=reason,
            actor_global_id=actor_global_id,
            admin_id=admin_id,
            admin_role=admin_role,
        ),
    )
