"""Staged, owner-scoped external Pay. No registration or activation here."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .shop_prepayment import Outcome, ShopRequest, ShopRequestError, freeze_review, verify_review
from .shop_prepayment_external_row import (
    ExternalPromotionRefused,
    link_new_external_intent,
    promote_selected_external_order,
)
from .shop_prepayment_store import PREPARATION_KEY, _Unit


async def pay_external(
    owner_wire: str, request: ShopRequest, review_id: str, *, store: Any, ops: Any,
) -> dict:
    if request.method not in {"TON", "USDT"}:
        raise ShopRequestError("SHOP_REQUEST_METHOD_UNAVAILABLE")
    owner_id = int(owner_wire)
    async with store.session_factory() as db:
        async with db.begin():
            unit = _Unit(db, owner_id, store.sql, store.resolve_type)
            # Preliminary read only decides whether to take an item lock.
            # Replay/status does not depend on the current catalog.
            seen = await unit.find(request.key)
            if seen is not None and seen.request != request:
                raise ShopRequestError("SHOP_REQUEST_PAYLOAD_MISMATCH")
            item = None
            lock_failure = None
            if seen is not None and seen.outcome is Outcome.PREPARED:
                try:
                    # Preserve legacy VIP item -> owner lock ordering.
                    item = await ops.lock_item(db, owner_id, request)
                except ShopRequestError as exc:
                    lock_failure = exc
            owner = await store.owner_lock(db, global_id=owner_id)
            if owner.global_id != owner_id:
                raise ShopRequestError("SHOP_REQUEST_TRANSITION_REFUSED")
            prior = await unit.find(request.key)
            if prior is not None and prior.request != request:
                raise ShopRequestError("SHOP_REQUEST_PAYLOAD_MISMATCH")
            if prior is None or prior.outcome is Outcome.CANCELED:
                raise ShopRequestError("SHOP_REQUEST_NOT_PREPARED")
            row = await unit._row(request.key)
            prepared = row["extra"][PREPARATION_KEY]
            verify_review(freeze_review(owner_id, request, prepared), review_id)
            if prior.outcome is not Outcome.PREPARED:
                output = {"state": prior.outcome.value}
                if prior.references is not None:
                    output.update(order_id=prior.references.order_id, intent_id=prior.references.intent_id)
                return output
            if lock_failure is not None:
                raise lock_failure
            if item is None:
                raise ShopRequestError("SHOP_REQUEST_TRANSITION_REFUSED")
            if await unit.lane_busy(except_key=request.key):
                raise ShopRequestError("SHOP_REQUEST_ACTIVE")
            oid = int(row["id"])
            try:
                output = await ops.issue(db, store.sql, item, owner_wire, oid, request, prepared)
            except ExternalPromotionRefused as exc:
                raise ShopRequestError(str(exc)) from exc
    # An exception or ambiguous commit cannot release wallet instructions.
    return output


class CanonicalExternalPay:
    async def lock_item(self, db, owner_id, req):
        from app.services.shop_service import _get_item_by_code, _lock_selected_vip_number_for_checkout

        try:
            item = await _get_item_by_code(db, req.sku)
            await _lock_selected_vip_number_for_checkout(
                db, item=item, global_id=owner_id, idempotency_key=req.key,
            )
            return item
        except ValueError as exc:
            raise ShopRequestError("SHOP_REQUEST_ITEM_UNAVAILABLE") from exc

    async def issue(self, db, sql, item, owner_wire, oid, req, prepared):
        from app.schemas.hub_schemas import BrowserShopCreateIntentOut
        from app.services import wallets_service
        from app.services.payment_intents_service import create_intent_shop_external_in_transaction
        from app.services.shop_service import (
            ShopService,
            _build_memo_for_external,
            _legacy_external_amount_d8,
            _normalize_custom_efhc_amount_d8,
            _order_extra,
            bind_vip_number_reservation_in_transaction,
            settings,
        )
        from app.services.transactions_service import IdempotencyPayloadConflictError

        owner = int(owner_wire)
        quote = prepared.get("quote")
        if not isinstance(quote, dict) or quote.get("item_type") != item.item_type:
            raise ShopRequestError("SHOP_REQUEST_SNAPSHOT_MISMATCH")
        catalog = await ShopService(db).get_catalog(0)
        if not any(str(entry.sku) == req.sku and bool(entry.active)
                   and entry.action_mode == "checkout" and req.method in (entry.methods or {})
                   for entry in catalog.items):
            raise ShopRequestError("SHOP_REQUEST_ITEM_UNAVAILABLE")
        wallets = await wallets_service.list_wallets(db, global_id=owner_wire)
        payer = next((w for w in wallets if w.is_primary and w.is_active and w.proof_verified), None)
        if payer is None:
            raise ShopRequestError("SHOP_REQUEST_WALLET_REQUIRED")
        receiver = str(getattr(settings, "TON_MAIN_WALLET", None) or "").strip()
        if not receiver or receiver != quote.get("to_address"):
            raise ShopRequestError("SHOP_REQUEST_SNAPSHOT_MISMATCH")
        preexisting = await db.execute(sql("""
            SELECT EXISTS (SELECT 1 FROM efhc_core.payment_intents
               WHERE global_id=:owner AND purpose='shop_external' AND idempotency_key=:key)
            """), {"owner": owner, "key": req.key})
        if preexisting.scalar_one():
            raise ShopRequestError("SHOP_REQUEST_ALREADY_ISSUED")
        custom = _normalize_custom_efhc_amount_d8(req.custom_efhc_amount_d8)
        expected = Decimal(quote["expected_amount"])
        quantity = quote.get("quantity_efhc")
        initial_memo = _build_memo_for_external(item, global_id=owner, custom_efhc_amount_d8=custom)
        snap = _order_extra(
            item, req.method, canonical_memo=initial_memo, request_quantity=req.quantity,
            unit_amount=expected, expected_amount=expected, to_address=receiver,
            external_amount_atomic=int(quote["external_amount_atomic"]),
            external_decimals=quote["external_decimals"], custom_efhc_amount_d8=custom,
        )
        # Preserve the canonical fingerprint's D8 value; the original prepared
        # JSON is used verbatim by the row compare.
        if snap["custom_efhc_amount_d8"] is not None and Decimal(snap["custom_efhc_amount_d8"]) != Decimal(prepared["custom"]):
            raise ShopRequestError("SHOP_REQUEST_SNAPSHOT_MISMATCH")
        await promote_selected_external_order(
            db, sql, owner=owner, order_id=oid, key=req.key, prepared=prepared,
            snapshot=snap, quantity_efhc=quantity,
            legacy_expected_amount=_legacy_external_amount_d8(expected),
        )
        try:
            intent = await create_intent_shop_external_in_transaction(
                db, global_id=owner_wire, idempotency_key=req.key, asset=req.method,
                to_address=receiver, external_amount_atomic=quote["external_amount_atomic"],
                efhc_amount_d8=quantity if item.item_type == "EFHC_PACKAGE" else "0",
            )
            reservation = await bind_vip_number_reservation_in_transaction(
                db, item_code=req.sku, global_id=owner, idempotency_key=req.key,
                order_id=oid, intent_id=int(intent["intent_id"]), expires_at=intent["expires_at"],
            )
        except (ValueError, IdempotencyPayloadConflictError) as exc:
            raise ShopRequestError("SHOP_REQUEST_TRANSITION_REFUSED") from exc
        if (intent.get("global_id") != owner_wire or intent.get("purpose") != "shop_external"
            or intent.get("asset") != req.method or intent.get("to_address") != receiver
            or intent.get("external_amount_atomic") != quote["external_amount_atomic"]
            or intent.get("external_decimals") != quote["external_decimals"]
            or Decimal(intent["external_amount_display"]) != expected):
            raise ShopRequestError("SHOP_REQUEST_SNAPSHOT_MISMATCH")
        iid = int(intent["intent_id"])
        payer_wallet = str(payer.wallet_address)
        await link_new_external_intent(
            db, sql, owner=owner, order_id=oid, key=req.key, prepared=prepared,
            snapshot=snap, intent_id=iid, quantity_efhc=quantity, intent_memo=intent["payload"],
            payer_wallet=payer_wallet, delivery_wallet=payer_wallet if item.item_type.startswith("NFT_VIP") else None,
            vip_number=str(reservation["number"]) if reservation else None,
        )
        fields = {
            "global_id": owner_wire, "intent_id": str(iid), "order_id": str(oid),
            "item_type": item.item_type, "pay_method": req.method,
            "amount": intent["external_amount_display"], "memo": intent["payload"],
            "to_wallet": receiver,
        }
        for field in (
            "external_amount_atomic", "external_decimals", "external_amount_display",
            "tonconnect_tx", "tonconnect_transport_kind", "jetton_master_address",
            "jetton_decimals", "forward_payload_text", "fee_message_ton_amount",
            "forward_ton_amount", "recipient_strategy", "usdt_checkout_mode", "expires_at",
        ):
            fields[field] = intent.get(field)
        payment = BrowserShopCreateIntentOut(**fields).model_dump(mode="json")
        return {"state": "issued", "order_id": str(oid), "intent_id": str(iid), "payment": payment}
