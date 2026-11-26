"""Staged VIP EFHC Pay; unregistered, uses the caller's single DB transaction."""

from collections.abc import Callable
from decimal import Decimal, InvalidOperation

from sqlalchemy import text

from app.identity.financial_write_owner import resolve_and_lock_financial_write_owner
from app.services import shop_service as shop
from app.services.shop_prepayment import ShopRequest, ShopRequestError
from app.services.shop_prepayment_store import (
    require_no_active_legacy_shop_intent,
    require_no_active_shop_preparation,
)


async def pay_prepared_vip_balance(
    db, *, verified_global_id: int, request: ShopRequest,
    review_id: str, require_review: Callable[[dict, str], None],
):
    """Call only after native auth, in a caller-owned transaction. Do not commit here."""
    if not db.in_transaction():
        raise RuntimeError("prepared VIP Pay needs an active transaction")
    if request.method != "EFHC" or request.quantity != 1 or not review_id:
        raise ShopRequestError("SHOP_REQUEST_INVALID")
    owner_id = int(verified_global_id)
    item = await shop._get_item_by_code(db, request.sku)
    if not shop._is_vip_item(item):
        raise ShopRequestError("SHOP_REQUEST_INVALID")
    # Canonical inventory locking comes first, before financial owner or order.
    await shop._lock_selected_vip_number_for_checkout(
        db, item=item, global_id=owner_id, idempotency_key=request.key,
    )
    owner = await resolve_and_lock_financial_write_owner(db, global_id=owner_id)
    if owner.global_id != owner_id:
        raise ShopRequestError("SHOP_REQUEST_INVALID")
    params = {"owner": owner_id, "key": request.key}
    row = (await db.execute(text("""
        SELECT id, status, created_at, expected_amount, extra,
               created_at + INTERVAL '15 minutes' > clock_timestamp() AS fresh
          FROM efhc_core.shop_orders
         WHERE global_id=:owner AND idempotency_key=:key FOR UPDATE
    """), params)).mappings().one_or_none()
    if row is None:
        raise ShopRequestError("SHOP_SELECTION_REQUIRED")
    saved = (row["extra"] or {}).get("shop_prepayment")
    if not isinstance(saved, dict) or any(saved.get(field) != expected for field, expected in (
        ("sku", request.sku), ("method", "EFHC"), ("quantity", 1), ("custom", None),
    )):
        raise ShopRequestError("SHOP_REQUEST_INVALID")
    quote = saved.get("quote")
    if not isinstance(quote, dict) or quote.get("item_type") != item.item_type:
        raise ShopRequestError("SHOP_REQUEST_INVALID")
    try:
        amount = Decimal(str(quote.get("expected_amount")))
        if not amount.is_finite() or amount <= 0 or amount != shop.d8(amount):
            raise ValueError("invalid amount")
    except (InvalidOperation, ValueError) as exc:
        raise ShopRequestError("SHOP_REQUEST_INVALID") from exc
    require_review(saved, review_id)
    paid = shop.ORDER_STATUS_PAID_PENDING_MANUAL
    order_id = int(row["id"])

    if row["status"] == "SELECTED" and row["fresh"] and shop.PAY_EFHC in item.pay_currencies:
        extra = shop._order_extra(item, shop.PAY_EFHC, request_quantity=1,
                                  unit_amount=amount, expected_amount=amount)
        import json
        result = await db.execute(text("""
            UPDATE efhc_core.shop_orders
               SET status=:paid, expected_amount=:amount, quantity_efhc=:quantity,
                   extra=extra || CAST(:extra AS jsonb), updated_at=clock_timestamp()
             WHERE id=:id AND global_id=:owner AND idempotency_key=:key AND status='SELECTED'
               AND created_at + INTERVAL '15 minutes' > clock_timestamp()
            RETURNING id
        """), {**params, "id": order_id, "paid": paid, "amount": amount,
                 "quantity": quote.get("quantity_efhc"), "extra": json.dumps(extra)})
        if result.scalar_one_or_none() != order_id:
            raise ShopRequestError("SHOP_SELECTION_EXPIRED")

        async def guard() -> None:
            await require_no_active_shop_preparation(db, global_id=owner_id)
            await require_no_active_legacy_shop_intent(db, global_id=owner_id)

        await shop.bank.spend_user_to_bank_bonus_then__main__nocommit(
            db, global_id=owner_id, amount=amount, reason=f"shop:{item.code}",
            idempotency_key=request.key, before_new_spend=guard,
            meta={"module": "shop_service", "item_code": item.code, "qty": 1,
                  "shop_expected_amount": str(amount)},
        )
        await shop._claim_selected_vip_number_in_transaction(
            db, item=item, global_id=owner_id, idempotency_key=request.key, order_id=order_id,
        )
    elif row["status"] != paid or row["expected_amount"] != amount:
        raise ShopRequestError("SHOP_SELECTION_NOT_PAYABLE")

    debited_bonus, debited_main, transfer_log_id = await shop._shop_spend_breakdown_from_ledger(
        db, global_id=owner_id, item_code=item.code, request_quantity=1,
        expected_amount=amount, idempotency_key=request.key,
    )
    return {"order_id": order_id, "status": paid, "debited_bonus_efhc": debited_bonus,
            "debited__main__efhc": debited_main, "bank_transfer_log_id": transfer_log_id}
