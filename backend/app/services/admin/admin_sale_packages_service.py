# backend/app/services/admin/admin_sale_packages_service.py
# =====================================================================
# Назначение:
# Админ-управление EFHC sale packages (pricing для deposit_efhc).
# =====================================================================

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.deps import d8
from app.lib.time import utcnow
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def list_packages(db: AsyncSession) -> list[dict[str, Any]]:
    q = text(
        "SELECT id, title, asset, "
        "price_asset_d8::numeric, efhc_amount_d8::numeric, "
        "COALESCE(is_active, TRUE) AS is_active "
        "FROM efhc_admin.efhc_sale_packages "
        "ORDER BY id ASC"
    )
    rows = (await db.execute(q)).mappings().all()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": int(r["id"]),
                "title": str(r["title"] or ""),
                "asset": str(r["asset"] or "TON"),
                "price_asset_d8": str(r["price_asset_d8"]),
                "efhc_amount_d8": str(r["efhc_amount_d8"]),
                "is_active": bool(r["is_active"]),
            }
        )
    return out


async def create_package(
    db: AsyncSession,
    *,
    title: str,
    asset: str,
    price_asset_d8: str,
    efhc_amount_d8: str,
    idempotency_key: str,
) -> dict[str, Any]:
    if not idempotency_key:
        raise ValueError("IDEMPOTENCY_REQUIRED")
    now = utcnow()
    price = d8(Decimal(str(price_asset_d8)))
    efhc = d8(Decimal(str(efhc_amount_d8)))

    q = text(
        "\n".join(
            [
                "INSERT INTO efhc_admin.efhc_sale_packages (",
                "  title, asset, price_asset_d8, efhc_amount_d8,",
                "  is_active, created_at, updated_at",
                ")",
                "VALUES (",
                "  :title, :asset, :price, :efhc,",
                "  TRUE, :now, :now",
                ")",
                "RETURNING id",
            ]
        )
    )
    r = await db.execute(
        q,
        {
            "title": str(title),
            "asset": str(asset).upper(),
            "price": price,
            "efhc": efhc,
            "now": now,
        },
    )
    new_id = int(r.scalar() or 0)
    await db.commit()
    return {
        "id": new_id,
        "title": str(title),
        "asset": str(asset).upper(),
        "price_asset_d8": str(price),
        "efhc_amount_d8": str(efhc),
        "is_active": True,
    }


async def toggle_package(
    db: AsyncSession,
    *,
    package_id: int,
) -> dict[str, Any]:
    now = utcnow()
    q = text(
        "\n".join(
            [
                "UPDATE efhc_admin.efhc_sale_packages",
                "   SET is_active = NOT COALESCE(is_active, TRUE),",
                "       updated_at = :now",
                " WHERE id = :pid",
                " RETURNING id, title, asset,",
                "   price_asset_d8::numeric, efhc_amount_d8::numeric,",
                "   COALESCE(is_active, TRUE) AS is_active",
            ]
        )
    )
    row = await db.execute(q, {"pid": int(package_id), "now": now})
    r = row.mappings().first()
    if not r:
        raise ValueError("PACKAGE_NOT_FOUND")
    await db.commit()
    return {
        "id": int(r["id"]),
        "title": str(r["title"] or ""),
        "asset": str(r["asset"] or "TON"),
        "price_asset_d8": str(r["price_asset_d8"]),
        "efhc_amount_d8": str(r["efhc_amount_d8"]),
        "is_active": bool(r["is_active"]),
    }


async def update_package(
    db: AsyncSession,
    *,
    package_id: int,
    title: str,
    asset: str,
    price_asset_d8: str,
    efhc_amount_d8: str,
) -> dict[str, Any]:
    now = utcnow()
    price = d8(Decimal(str(price_asset_d8)))
    efhc = d8(Decimal(str(efhc_amount_d8)))
    q = text(
        "\n".join(
            [
                "UPDATE efhc_admin.efhc_sale_packages",
                "   SET title = :title,",
                "       asset = :asset,",
                "       price_asset_d8 = :price,",
                "       efhc_amount_d8 = :efhc,",
                "       updated_at = :now",
                " WHERE id = :pid",
                " RETURNING id, title, asset,",
                "   price_asset_d8::numeric, efhc_amount_d8::numeric,",
                "   COALESCE(is_active, TRUE) AS is_active",
            ]
        )
    )
    row = (
        (
            await db.execute(
                q,
                {
                    "pid": int(package_id),
                    "title": str(title),
                    "asset": str(asset).upper(),
                    "price": price,
                    "efhc": efhc,
                    "now": now,
                },
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise ValueError("PACKAGE_NOT_FOUND")
    await db.commit()
    return {
        "id": int(row["id"]),
        "title": str(row["title"] or ""),
        "asset": str(row["asset"] or "USDT"),
        "price_asset_d8": str(row["price_asset_d8"]),
        "efhc_amount_d8": str(row["efhc_amount_d8"]),
        "is_active": bool(row["is_active"]),
    }
