"""Inactive narrow row-promotion seam. Not a public Pay handler.

Caller must run in the established VIP-item -> financial owner lock order,
reauthorize the verified wallet and revalidate stock/quote in that transaction.
There must be no commits in, or between, these statements and intent/reservation
composition. This module provides no payment transport or replay behavior.
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

_SELECT_TO_PENDING = """
UPDATE efhc_core.shop_orders
   SET status='PENDING', expected_amount=:expected_amount,
       quantity_efhc=:quantity_efhc, memo=:memo,
       extra=extra || CAST(:snapshot AS jsonb), updated_at=NOW()
 WHERE id=:order_id AND global_id=:owner AND idempotency_key=:key
   AND status='SELECTED' AND created_at + INTERVAL '15 minutes' > NOW()
   AND expected_amount IS NULL AND quantity_efhc IS NULL
   AND memo IS NULL AND tx_hash IS NULL
   AND NOT (extra ?| ARRAY['intent_id', 'intent_payload', 'payment_intent_kind'])
   AND extra->'shop_prepayment' = CAST(:prepared AS jsonb)
RETURNING id
"""

_LINK_NEW_INTENT = """
UPDATE efhc_core.shop_orders
   SET memo=:memo, extra=extra || jsonb_build_object(
       'intent_id', CAST(:intent_id AS bigint),
       'intent_payload', CAST(:memo AS text),
       'payment_owner_global_id', CAST(:owner_wire AS text),
       'payment_intent_kind', 'shop_external',
       'payer_wallet_address', CAST(:payer_wallet AS text),
       'delivery_wallet_address', CAST(:delivery_wallet AS text),
       'vip_number_reserved', CAST(:vip_number AS text)
   ), updated_at=NOW()
 WHERE id=:order_id AND global_id=:owner AND idempotency_key=:key
   AND status='PENDING' AND tx_hash IS NULL AND memo=:initial_memo
   AND NOT (extra ?| ARRAY['intent_id', 'intent_payload', 'payment_intent_kind'])
   AND extra->'shop_prepayment' = CAST(:prepared AS jsonb)
   AND extra->>'payment_method' = :method
   AND extra->>'external_amount_atomic' = :external_atomic
   AND extra->>'to_address' = :receiver
   AND EXISTS (
       SELECT 1 FROM efhc_core.payment_intents AS i
        WHERE i.id=:intent_id AND i.global_id=:owner AND i.purpose='shop_external'
          AND i.idempotency_key=:key AND i.status='PENDING' AND i.expires_at > NOW()
          AND i.asset=:method AND i.to_address=:receiver AND i.payload=:memo
   )
RETURNING id
"""


class ExternalPromotionRefused(ValueError):
    pass


def _account_order_key(db: Any, owner: int, order_id: int, key: str) -> dict[str, Any]:
    if not db.in_transaction():
        raise ExternalPromotionRefused("SHOP_REQUEST_TRANSACTION_REQUIRED")
    if (type(owner) is not int or owner <= 0 or type(order_id) is not int
        or order_id <= 0 or not isinstance(key, str) or not key.strip()
        or key != key.strip() or len(key) > 128):
        raise ExternalPromotionRefused("SHOP_REQUEST_INVALID")
    return {"owner": owner, "order_id": order_id, "key": key}


def _snapshot_args(prepared: dict[str, Any], snapshot: dict[str, Any], quantity_efhc: str | None) -> dict[str, Any]:
    # A frozen server-side quote is mandatory; no reprice or client quote.
    quote = prepared.get("quote")
    if not isinstance(quote, dict):
        raise ExternalPromotionRefused("SHOP_REQUEST_SNAPSHOT_MISMATCH")
    amount = snapshot.get("expected_amount")
    atomic = snapshot.get("external_amount_atomic")
    decimals = snapshot.get("external_decimals")
    method = snapshot.get("payment_method")
    given_custom = snapshot.get("custom_efhc_amount_d8")
    saved_custom = prepared.get("custom")
    try:
        custom_matches = (given_custom is None and saved_custom is None) or (
            given_custom is not None and saved_custom is not None
            and Decimal(given_custom) == Decimal(saved_custom)
        )
    except (ValueError, ArithmeticError, TypeError):
        custom_matches = False
    if (
        method not in {"TON", "USDT"}
        or method != prepared.get("method")
        or not isinstance(prepared.get("sku"), str) or not prepared["sku"]
        or snapshot.get("sku") != prepared["sku"]
        or type(prepared.get("quantity")) is not int or prepared["quantity"] != 1
        or snapshot.get("request_quantity") != 1
        or not custom_matches
        or not isinstance(amount, str) or not 1 <= len(amount) <= 40
        or not isinstance(atomic, str) or not 1 <= len(atomic) <= 39
        or not atomic.isascii() or not atomic.isdecimal() or int(atomic) <= 0
        or type(decimals) is not int or decimals != (9 if method == "TON" else 6)
        or quote.get("external_amount_atomic") != atomic
        or quote.get("external_decimals") != decimals
        or quote.get("expected_amount") != amount
        or quote.get("to_address") != snapshot.get("to_address")
        or not isinstance(quote.get("item_type"), str) or not quote["item_type"]
        or quote["item_type"] != snapshot.get("item_type")
        or quote.get("quantity_efhc") != quantity_efhc
        or not isinstance(snapshot.get("canonical_memo"), str) or not snapshot["canonical_memo"]
        or not isinstance(snapshot.get("to_address"), str) or not snapshot["to_address"]
        or any(k in snapshot for k in ("shop_prepayment", "intent_id", "intent_payload",
                                        "payment_intent_kind", "payer_wallet_address",
                                        "delivery_wallet_address", "vip_number_reserved"))
    ):
        raise ExternalPromotionRefused("SHOP_REQUEST_SNAPSHOT_MISMATCH")
    if not all(part.isascii() and part.isdecimal() for part in amount.split(".", maxsplit=1)):
        raise ExternalPromotionRefused("SHOP_REQUEST_SNAPSHOT_MISMATCH")
    # Compare atomic units in decimal arithmetic, never binary floating point.
    try:
        numerator, denominator = Decimal(amount).as_integer_ratio()
    except (ValueError, OverflowError, ArithmeticError) as exc:
        raise ExternalPromotionRefused("SHOP_REQUEST_SNAPSHOT_MISMATCH") from exc
    if numerator * 10**decimals != int(atomic) * denominator:
        raise ExternalPromotionRefused("SHOP_REQUEST_SNAPSHOT_MISMATCH")
    return {"prepared": json.dumps(prepared), "method": method,
            "receiver": snapshot["to_address"], "external_atomic": atomic,
            "initial_memo": snapshot["canonical_memo"], "expected_amount": amount}


async def _guarded_update(db: Any, sql: Any, query: str, args: dict[str, Any]) -> int:
    result = await db.execute(sql(query), args)
    returned = result.scalar_one_or_none()
    if returned != args["order_id"]:
        raise ExternalPromotionRefused("SHOP_REQUEST_TRANSITION_REFUSED")
    return returned


async def promote_selected_external_order(
    db: Any, sql: Any, *, owner: int, order_id: int, key: str,
    prepared: dict[str, Any], snapshot: dict[str, Any], quantity_efhc: str | None,
    legacy_expected_amount: Decimal | None = None,
) -> int:
    """Stage only; existing intent and reservation must follow in this same transaction."""
    args = _account_order_key(db, owner, order_id, key)
    fields = _snapshot_args(prepared, snapshot, quantity_efhc)
    return await _guarded_update(db, sql, _SELECT_TO_PENDING, {
        **args, "prepared": fields["prepared"], "expected_amount": str(legacy_expected_amount) if legacy_expected_amount is not None else fields["expected_amount"],
        "quantity_efhc": quantity_efhc, "memo": fields["initial_memo"], "snapshot": json.dumps(snapshot),
    })


async def link_new_external_intent(
    db: Any, sql: Any, *, owner: int, order_id: int, key: str,
    prepared: dict[str, Any], snapshot: dict[str, Any], intent_id: int, quantity_efhc: str | None,
    intent_memo: str, payer_wallet: str, delivery_wallet: str | None, vip_number: str | None,
) -> int:
    """Attach only a coherent owner/key-linked pending intent; no synthetic success."""
    args = _account_order_key(db, owner, order_id, key)
    fields = _snapshot_args(prepared, snapshot, quantity_efhc)
    if (type(intent_id) is not int or intent_id <= 0
        or not isinstance(intent_memo, str) or not intent_memo.strip()
        or not isinstance(payer_wallet, str) or not payer_wallet.strip()):
        raise ExternalPromotionRefused("SHOP_REQUEST_INTENT_INCOMPLETE")
    return await _guarded_update(db, sql, _LINK_NEW_INTENT, {
        **args, **{k:v for k,v in fields.items() if k != "expected_amount"},
        "intent_id": intent_id, "memo": intent_memo, "owner_wire": str(owner).zfill(10),
        "payer_wallet": payer_wallet, "delivery_wallet": delivery_wallet, "vip_number": vip_number,
    })
