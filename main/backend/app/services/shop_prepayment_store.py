"""Existing ShopOrder preparation; no schema changes, payment inputs or issuer."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any

from .shop_prepayment import Attempt, Outcome, References, ShopRequest, ShopRequestError, freeze_review

PREPARATION_KEY = "shop_prepayment"
SELECTED = "SELECTED"
WITHDRAWN = "SELECTION_CANCELED"
LEGACY_BLOCKED = "SHOP_REQUEST_ACTIVE"
PREPAYMENT_ORDERS_FILTER = "status NOT IN ('SELECTED', 'SELECTION_CANCELED')"

_LEGACY_LANE = """
SELECT EXISTS (
    SELECT 1 FROM efhc_core.payment_intents
     WHERE global_id=:owner AND purpose='shop_external'
       AND status='PENDING' AND expires_at > NOW()
)
"""
_SELECTED_LANE = """
SELECT EXISTS (
    SELECT 1 FROM efhc_core.shop_orders
     WHERE global_id=:owner AND status='SELECTED'
       AND extra ? 'shop_prepayment'
       AND created_at + INTERVAL '15 minutes' > NOW()
       AND (CAST(:except_key AS text) IS NULL OR idempotency_key <> :except_key)
)
"""
_ORDER = """
SELECT so.status,so.id,so.extra,pi.id AS linked_intent_id,
       pi.status AS linked_intent_status, so.tx_hash,
       so.created_at + INTERVAL '15 minutes' > NOW() AS selection_fresh
  FROM efhc_core.shop_orders AS so
  LEFT JOIN efhc_core.payment_intents AS pi
    ON pi.global_id=so.global_id AND pi.idempotency_key=so.idempotency_key
   AND pi.purpose='shop_external' AND CAST(pi.id AS text)=so.extra->>'intent_id'
 WHERE so.global_id=:owner AND so.idempotency_key=:key
"""
_INSERT = """
INSERT INTO efhc_core.shop_orders (global_id,type,status,idempotency_key,extra)
VALUES (:owner,:kind,:state,:key,CAST(:extra AS jsonb))
ON CONFLICT (global_id,idempotency_key) DO NOTHING
RETURNING id
"""
_CANCEL = """
UPDATE efhc_core.shop_orders
   SET status='SELECTION_CANCELED', updated_at=NOW()
 WHERE global_id=:owner AND idempotency_key=:key AND status='SELECTED'
   AND extra ? 'shop_prepayment'
RETURNING id
"""


class ShopPreparationActiveError(ValueError):
    """A legacy new operation cannot bypass an active owned preparation."""


async def require_no_active_shop_preparation(db: Any, *, global_id: int) -> None:
    """Use only after acquiring the existing canonical owner row lock."""
    from sqlalchemy import text

    result = await db.execute(text(_SELECTED_LANE), {"owner": global_id, "except_key": None})
    if result.scalar_one():
        raise ShopPreparationActiveError(LEGACY_BLOCKED)


async def require_no_active_legacy_shop_intent(db: Any, *, global_id: int) -> None:
    """Additional Shop balance guard under the same canonical owner lock."""
    from sqlalchemy import text

    result = await db.execute(text(_LEGACY_LANE), {"owner": global_id})
    if result.scalar_one():
        raise ShopPreparationActiveError("SHOP_EXTERNAL_INTENT_ACTIVE")


class _Unit:
    def __init__(self, db: Any, owner: int, sql: Any, resolve_type: Any) -> None:
        self.db, self.owner, self.sql, self.resolve_type = db, owner, sql, resolve_type

    async def _row(self, key: str) -> Any:
        result = await self.db.execute(self.sql(_ORDER), {"owner": self.owner, "key": key})
        return result.mappings().one_or_none()

    async def find(self, key: str) -> Attempt | None:
        row = await self._row(key)
        if row is None:
            return None
        extra = row["extra"] or {}
        snapshot = extra.get(PREPARATION_KEY)
        if not isinstance(snapshot, dict):
            # Never cancel or reinterpret a legacy payment by key.
            raise ShopRequestError("SHOP_REQUEST_ALREADY_ISSUED")
        req = ShopRequest(
            key, snapshot["sku"], snapshot["method"], snapshot["quantity"],
            Decimal(snapshot["custom"]) if snapshot["custom"] is not None else None,
        )
        state = row["status"]
        if state == WITHDRAWN:
            return Attempt(req, Outcome.CANCELED)
        if state == SELECTED:
            if not row["selection_fresh"]:
                return Attempt(req, Outcome.TERMINAL_UNPAID)
            review = freeze_review(self.owner, req, snapshot)
            if review is None:
                raise ShopRequestError("SHOP_REQUEST_REVIEW_UNAVAILABLE")
            return Attempt(req, Outcome.PREPARED, review=review)
        linked = row.get("linked_intent_id")
        refs = References(str(row["id"]), str(linked)) if linked else None
        if linked and row.get("linked_intent_status") == "CONFIRMED" and row.get("tx_hash") and state in {
            "PAID_AUTO", "FULFILLED", "PAID_PENDING_MANUAL", "APPROVED", "REJECTED",
        }:
            return Attempt(req, Outcome.PAID, refs)
        if (linked and row.get("linked_intent_status") == "EXPIRED"
                and not row.get("tx_hash") and state == "PENDING"):
            return Attempt(req, Outcome.TERMINAL_UNPAID, refs)
        return Attempt(req, Outcome.ISSUED, refs)

    async def lane_busy(self, *, except_key: str | None = None) -> bool:
        selected = await self.db.execute(self.sql(_SELECTED_LANE), {
            "owner": self.owner, "except_key": except_key,
        })
        if selected.scalar_one():
            return True
        legacy = await self.db.execute(self.sql(_LEGACY_LANE), {"owner": self.owner})
        return legacy.scalar_one()

    async def save(self, attempt: Attempt) -> None:
        if attempt.outcome not in {Outcome.PREPARED, Outcome.CANCELED} or attempt.references:
            raise ShopRequestError("SHOP_REQUEST_ISSUE_DISABLED")
        req = attempt.request
        args = {"owner": self.owner, "key": req.key}
        if attempt.outcome == Outcome.CANCELED and await self._row(req.key) is not None:
            result = await self.db.execute(self.sql(_CANCEL), args)
        else:
            # Tombstone is an internal row, not a catalog item assertion. The
            # legacy required type slot is neutral and hidden from order views.
            kind, quote = (
                ("EFHC", None) if attempt.outcome == Outcome.CANCELED
                else await self.resolve_type(self.db, req)
            )
            result = await self.db.execute(self.sql(_INSERT), {
                **args, "state": SELECTED if attempt.outcome == Outcome.PREPARED else WITHDRAWN,
                "kind": kind, "extra": json.dumps({PREPARATION_KEY: {
                    "sku": req.sku, "method": req.method, "quantity": req.quantity,
                    "custom": str(req.custom_efhc_amount_d8)
                    if req.custom_efhc_amount_d8 is not None else None,
                    "quote": quote,
                }}),
            })
        if result.scalar_one_or_none() is None:
            raise ShopRequestError("SHOP_REQUEST_TRANSITION_REFUSED")

    async def issue(self, request: ShopRequest) -> References:
        raise ShopRequestError("SHOP_REQUEST_ISSUE_DISABLED")


class PostgresCheckoutStore:
    def __init__(self, session_factory: Any, owner_lock: Any, sql: Any, resolve_type: Any = None) -> None:
        self.session_factory, self.owner_lock, self.sql = session_factory, owner_lock, sql
        self.resolve_type = resolve_type

    @asynccontextmanager
    async def owner_unit(self, verified_owner: str, *, issuing: ShopRequest | None = None):
        if issuing is not None:
            raise ShopRequestError("SHOP_REQUEST_ISSUE_DISABLED")
        async with self.session_factory() as db:
            async with db.begin():
                owner = await self.owner_lock(db, global_id=int(verified_owner))
                yield _Unit(db, owner.global_id, self.sql, self.resolve_type)


async def _resolve_type(db: Any, request: ShopRequest) -> tuple[str, dict]:
    from app.services.shop_service import (
        ITEM_TYPE_EFHC_PACKAGE, _get_item_by_code, _order_type_for_item,
        _quote_external_checkout_amount,
        _scaled_item_quantity_text, d8, settings,
    )

    try:
        item = await _get_item_by_code(db, request.sku)
        if request.method not in item.pay_currencies:
            raise ValueError("method unavailable")
        kind = _order_type_for_item(item)
        quote: dict = {"item_type": item.item_type}
        if request.method == "EFHC":
            if (item.item_type == ITEM_TYPE_EFHC_PACKAGE or item.price_efhc is None
                    or item.price_efhc <= 0):
                raise ValueError("price unavailable")
            if request.custom_efhc_amount_d8 is not None:
                raise ValueError("inapplicable custom amount")
            quote["expected_amount"] = str(d8(d8(item.price_efhc) * Decimal(request.quantity)))
            custom = None
        else:
            external, custom = _quote_external_checkout_amount(
                item, request.method, request.custom_efhc_amount_d8
            )
            receiver = str(getattr(settings, "TON_MAIN_WALLET", None) or "").strip()
            if not receiver:
                raise ValueError("receiver unavailable")
            quote.update({
                "expected_amount": str(external.display),
                "external_amount_atomic": str(external.atomic),
                "external_decimals": external.decimals,
                "to_address": receiver,
            })
        quote["quantity_efhc"] = _scaled_item_quantity_text(
            item, request.quantity, custom_efhc_amount_d8=custom,
        )
    except ValueError as exc:
        raise ShopRequestError("SHOP_REQUEST_INVALID") from exc
    return kind, quote


def build_local_store() -> PostgresCheckoutStore:
    from app.core.database_core import new_session
    from app.identity.financial_write_owner import resolve_and_lock_financial_write_owner
    from sqlalchemy import text

    return PostgresCheckoutStore(new_session, resolve_and_lock_financial_write_owner, text, _resolve_type)
