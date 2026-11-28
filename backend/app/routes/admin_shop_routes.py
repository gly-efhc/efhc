# backend/app/routes/admin_shop_routes.py
# ======================================================================
# EFHC Bot — административные маршруты Shop
# ----------------------------------------------------------------------
# Назначение:
# Admin-layer для `/admin/shop`. Hub manager вынесен в
# отдельный router module и не вкладывается в shop router.
#
# Канон:
# • Только global_id во внешнем слое.
# ======================================================================

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal, cast

from app.core.logging_core import get_logger
from app.deps import get_db, require_admin, require_admin_write
from app.domain.finance.shop_prices import (
    SHOP_PRICE_ERROR_CODES,
    normalize_shop_external_price_d2,
)
from app.identity.api_contract import ApiExternalGlobalId
from app.schemas.id_schemas import ApiLifetimeId
from app.services.admin.admin_shop_service import (
    admin_delete_item,
    admin_force_fulfill_order,
    admin_list_items,
    admin_list_orders,
    admin_order_status_counters,
    admin_set_item_status,
    admin_set_price,
    admin_upsert_item,
)
from app.services.admin.admin_vip_nft_service import (
    decide_vip_nft_request,
    list_vip_nft_requests,
)
from app.services.orders_service import get_order, list_user_orders
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/admin/shop", tags=["admin:shop"])
logger = get_logger(__name__)


class AdminOrderOut(BaseModel):
    order_id: ApiLifetimeId
    global_id: str | None = None
    status: str
    type: str
    item_code: str | None = None
    payment_method: str | None = None
    quantity_efhc: str | None = None
    expected_amount: str | None = None
    tx_hash: str | None = None
    memo: str | None = None
    payment_error_log: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    paid_at: str | None = None
    fulfilled_at: str | None = None


def _order_to_out(order: Any) -> AdminOrderOut:
    raw_order_id = getattr(order, "order_id", None)
    if raw_order_id is None:
        raw_order_id = getattr(order, "id", 0)
    order_id = 0 if raw_order_id is None else int(raw_order_id)
    extra = getattr(order, "extra", None) or {}
    if not isinstance(extra, dict):
        extra = {}
    return AdminOrderOut(
        order_id=order_id,
        global_id=(
            f"{int(order.global_id):010d}"
            if getattr(order, "global_id", None) is not None
            else None
        ),
        status=str(getattr(order, "status", "")),
        type=str(getattr(order, "type", "")),
        item_code=str(extra.get("sku") or "") or None,
        payment_method=(
            str(extra.get("payment_method") or "") or None
        ),
        quantity_efhc=(
            str(order.quantity_efhc)
            if getattr(order, "quantity_efhc", None) is not None
            else None
        ),
        expected_amount=(
            str(order.expected_amount)
            if getattr(order, "expected_amount", None) is not None
            else None
        ),
        tx_hash=getattr(order, "tx_hash", None),
        memo=getattr(order, "memo", None),
        payment_error_log=getattr(order, "payment_error_log", None),
        created_at=(
            order.created_at.isoformat()
            if getattr(order, "created_at", None) is not None
            else None
        ),
        updated_at=(
            order.updated_at.isoformat()
            if getattr(order, "updated_at", None) is not None
            else None
        ),
        paid_at=(
            order.paid_at.isoformat()
            if getattr(order, "paid_at", None) is not None
            else None
        ),
        fulfilled_at=(
            order.fulfilled_at.isoformat()
            if getattr(order, "fulfilled_at", None) is not None
            else None
        ),
    )


class AdminShopItemOut(BaseModel):
    id: ApiLifetimeId
    code: str
    sku: str
    title: str
    description: str = ""
    item_type: str
    is_active: bool
    status: str = "draft"
    quantity_efhc: str = ""
    image_url: str = ""
    price_efhc: str = ""
    price_ton: str = ""
    price_usdt: str = ""
    price_diagnostics: dict[str, str] = Field(default_factory=dict)
    pay_currencies: list[str] = Field(default_factory=list)
    category: str = "other"
    badge: str = ""
    action_mode: str = "checkout"
    external_url: str = ""
    delivery_mode: str = "manual"
    sort_order: int = 0
    history_count: int = 0
    history_tail: list[dict[str, Any]] = Field(default_factory=list)


class AdminShopItemUpsertIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    item_type: str = Field(
        default="EFHC_PACKAGE",
        min_length=1,
        max_length=64,
    )
    quantity_efhc: Decimal | None = None
    image_url: str | None = Field(default=None, max_length=2048)
    status: str = Field(default="draft", min_length=1, max_length=16)
    price_efhc: Decimal | None = None
    price_ton: Decimal | None = None
    price_usdt: Decimal | None = None
    pay_currencies: list[str] | None = None
    category: str | None = Field(default=None, max_length=64)
    badge: str | None = Field(default=None, max_length=64)
    action_mode: str = Field(default="checkout", max_length=32)
    external_url: str | None = Field(default=None, max_length=2048)
    delivery_mode: str | None = Field(default=None, max_length=32)
    sort_order: int = Field(default=0, ge=-100000, le=100000)

    @field_validator("price_ton", "price_usdt")
    @classmethod
    def _shop_external_price_d2(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        normalized: Decimal = normalize_shop_external_price_d2(value)
        return normalized


class SetPriceIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    price_efhc: Decimal | None = None
    price_ton: Decimal | None = None
    price_usdt: Decimal | None = None
    pay_currencies: list[str] | None = None
    is_active: bool | None = None

    @field_validator("price_ton", "price_usdt")
    @classmethod
    def _shop_external_price_d2(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        normalized: Decimal = normalize_shop_external_price_d2(value)
        return normalized


class SetItemStatusIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    status: str = Field(..., min_length=1, max_length=16)


class DeleteItemIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)


class ForceFulfillOrderIn(BaseModel):
    reason: str | None = Field(default=None, max_length=512)


class NftRequestDecisionIn(BaseModel):
    decision: Literal["issued", "rejected"]
    reason: str = Field(..., min_length=1, max_length=512)
    delivery_tx_hash: str | None = Field(default=None, max_length=128)


@router.get("/orders")
async def admin_orders(
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
    status: str | None = None,
    item_type: str | None = None,
    global_id: ApiExternalGlobalId | None = None,
    db: AsyncSession = Depends(get_db),
    _auth: Any = Depends(require_admin),
) -> dict[str, Any]:
    """Админский список заказов магазина с курсорной пагинацией."""
    try:
        return cast(
            dict[str, Any],
            await admin_list_orders(
                db,
                limit=int(limit),
                cursor=cursor,
                status=status,
                item_type=item_type,
                global_id=(
                    int(global_id)
                    if global_id is not None
                    else None
                ),
            ),
        )
    except Exception:
        logger.exception("admin orders failed")
        raise HTTPException(
            status_code=500,
            detail="ADMIN_ORDERS_UNAVAILABLE",
        ) from None


@router.get("/orders/status-counters")
async def admin_shop_order_status_counters(
    db: AsyncSession = Depends(get_db),
    _auth: Any = Depends(require_admin),
) -> dict[str, Any]:
    """Глобальный Shop dashboard по всем заказам, а не только UI-странице."""
    try:
        return cast(
            dict[str, Any],
            await admin_order_status_counters(db),
        )
    except Exception:
        logger.exception("admin order counters failed")
        raise HTTPException(
            status_code=500,
            detail="ADMIN_ORDER_COUNTERS_UNAVAILABLE",
        ) from None


@router.post("/orders/{order_id}/force-fulfill")
async def admin_force_fulfill_shop_order(
    order_id: ApiLifetimeId,
    payload: ForceFulfillOrderIn,
    db: AsyncSession = Depends(get_db),
    auth: Any = Depends(require_admin_write),
) -> dict[str, Any]:
    try:
        return cast(
            dict[str, Any],
            await admin_force_fulfill_order(
                db,
                order_id=int(order_id),
                reason=payload.reason,
                actor_global_id=int(auth.global_id),
                admin_id=int(auth.admin_id),
                admin_role=str(auth.role),
            ),
        )
    except ValueError as e:
        status_code = 404 if str(e) == "ORDER_NOT_FOUND" else 409
        raise HTTPException(status_code=status_code, detail=str(e)) from e
    except Exception:
        logger.exception("force fulfill failed")
        raise HTTPException(
            status_code=500,
            detail="ADMIN_FORCE_FULFILL_UNAVAILABLE",
        ) from None


@router.get("/nft-requests")
async def admin_vip_nft_requests(
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _auth: Any = Depends(require_admin),
) -> dict[str, Any]:
    """Очередь оплаченных заявок на ручную выдачу VIP NFT."""

    return cast(
        dict[str, Any],
        await list_vip_nft_requests(
            db,
            limit=int(limit),
            cursor=cursor,
            status=status,
        ),
    )


@router.post("/nft-requests/{order_id}/decision")
async def admin_vip_nft_request_decision(
    order_id: ApiLifetimeId,
    payload: NftRequestDecisionIn,
    db: AsyncSession = Depends(get_db),
    auth: Any = Depends(require_admin_write),
) -> dict[str, Any]:
    """Подтвердить фактическую выдачу NFT или отклонить заявку."""

    try:
        return cast(
            dict[str, Any],
            await decide_vip_nft_request(
                db,
                order_id=int(order_id),
                decision=payload.decision,
                reason=payload.reason,
                delivery_tx_hash=payload.delivery_tx_hash,
                actor_global_id=int(auth.global_id),
            ),
        )
    except ValueError as exc:
        code = str(exc)
        http_status = 404 if code == "NFT_REQUEST_NOT_FOUND" else 409
        raise HTTPException(status_code=http_status, detail=code) from exc


@router.get("/items", response_model=list[AdminShopItemOut])
async def admin_items(
    db: AsyncSession = Depends(get_db),
    _auth: Any = Depends(require_admin),
) -> list[AdminShopItemOut]:
    try:
        rows = await admin_list_items(db)
        return [AdminShopItemOut.model_validate(row) for row in rows]
    except Exception:
        logger.exception("admin items failed")
        raise HTTPException(
            status_code=500,
            detail="ADMIN_ITEMS_UNAVAILABLE",
        ) from None


@router.post("/items/upsert")
async def admin_upsert_shop_item(
    payload: AdminShopItemUpsertIn,
    db: AsyncSession = Depends(get_db),
    _auth: Any = Depends(require_admin_write),
) -> dict[str, Any]:
    try:
        return cast(
            dict[str, Any],
            await admin_upsert_item(
                db,
                code=payload.code,
                title=payload.title,
                description=payload.description,
                item_type=payload.item_type,
                quantity_efhc=payload.quantity_efhc,
                image_url=payload.image_url,
                status=payload.status,
                price_efhc=payload.price_efhc,
                price_ton=payload.price_ton,
                price_usdt=payload.price_usdt,
                pay_currencies=payload.pay_currencies,
                category=payload.category,
                badge=payload.badge,
                action_mode=payload.action_mode,
                external_url=payload.external_url,
                delivery_mode=payload.delivery_mode,
                sort_order=payload.sort_order,
            ),
        )
    except ValueError as exc:
        code = str(exc)
        if code in SHOP_PRICE_ERROR_CODES:
            raise HTTPException(status_code=422, detail=code) from None
        logger.warning("admin upsert item rejected: %s", code)
        raise HTTPException(status_code=400, detail=code) from None
    except Exception:
        logger.exception("admin upsert item failed")
        raise HTTPException(
            status_code=500,
            detail="ADMIN_ITEM_UPSERT_UNAVAILABLE",
        ) from None


@router.get("/order/{order_id}", response_model=AdminOrderOut)
async def admin_get_order(
    order_id: ApiLifetimeId,
    db: AsyncSession = Depends(get_db),
    _auth: Any = Depends(require_admin),
) -> AdminOrderOut:
    """Прочитать заказ по canonical order ID."""
    try:
        order = await get_order(db, order_id=int(order_id))
    except Exception:
        logger.exception("admin order read failed")
        raise HTTPException(
            status_code=500,
            detail="ADMIN_ORDER_READ_UNAVAILABLE",
        ) from None
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return _order_to_out(order)


@router.get(
    "/orders/user/{global_id}",
    response_model=list[AdminOrderOut],
)
async def admin_list_user_orders(
    global_id: ApiExternalGlobalId,
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _auth: Any = Depends(require_admin),
) -> list[AdminOrderOut]:
    """Список заказов canonical аккаунта по global_id."""
    try:
        rows = await list_user_orders(
            db,
            global_id=int(global_id),
            limit=int(limit),
        )
    except Exception:
        logger.exception("admin user orders failed")
        raise HTTPException(
            status_code=500,
            detail="ADMIN_USER_ORDERS_UNAVAILABLE",
        ) from None
    return [_order_to_out(order) for order in rows]


@router.post("/items/status")
async def admin_set_shop_item_status(
    payload: SetItemStatusIn,
    db: AsyncSession = Depends(get_db),
    _auth: Any = Depends(require_admin_write),
) -> dict[str, Any]:
    try:
        return cast(
            dict[str, Any],
            await admin_set_item_status(
                db,
                code=payload.code,
                status=payload.status,
            ),
        )
    except Exception:
        logger.exception("admin set item status failed")
        raise HTTPException(
            status_code=500,
            detail="ADMIN_ITEM_STATUS_UNAVAILABLE",
        ) from None


# Маршрут совместимости: отдельный редактор цены больше не нужен.
# Канонический Admin Shop Editor использует /items/upsert; этот маршрут
# сохранён для старых операторских интеграций и делегирует тому же Shop-хранилищу.
@router.post("/items/set-price")
async def admin_set_item_price(
    payload: SetPriceIn,
    db: AsyncSession = Depends(get_db),
    _auth: Any = Depends(require_admin_write),
) -> dict[str, Any]:
    """Совместимо обновить цены/валюты карточки по canonical SKU."""
    try:
        return cast(
            dict[str, Any],
            await admin_set_price(
                db,
                code=payload.code,
                price_efhc=payload.price_efhc,
                price_ton=payload.price_ton,
                price_usdt=payload.price_usdt,
                pay_currencies=payload.pay_currencies,
                is_active=payload.is_active,
            ),
        )
    except ValueError as exc:
        code = str(exc)
        if code in SHOP_PRICE_ERROR_CODES:
            raise HTTPException(status_code=422, detail=code) from None
        logger.warning("admin set price rejected: %s", code)
        raise HTTPException(status_code=400, detail=code) from None
    except Exception:
        logger.exception("admin set price failed")
        raise HTTPException(
            status_code=500,
            detail="ADMIN_ITEM_PRICE_UNAVAILABLE",
        ) from None


@router.post("/items/delete")
async def admin_delete_shop_item(
    payload: DeleteItemIn,
    db: AsyncSession = Depends(get_db),
    _auth: Any = Depends(require_admin_write),
) -> dict[str, Any]:
    try:
        return cast(
            dict[str, Any],
            await admin_delete_item(
                db,
                code=payload.code,
            ),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=409,
            detail=f"admin delete item blocked: {e}",
        ) from e
    except Exception:
        logger.exception("admin delete item failed")
        raise HTTPException(
            status_code=500,
            detail="ADMIN_ITEM_DELETE_UNAVAILABLE",
        ) from None
