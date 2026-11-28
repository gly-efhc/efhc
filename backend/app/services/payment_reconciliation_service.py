from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.deps import d8
from app.domain.finance.external_amounts import (
    external_amount_from_atomic,
)
from app.identity.types import global_id_to_database, parse_global_id
from app.services.financial_execution_window import (
    validate_external_financial_execution,
)
from app.services.intent_payload_parsing_service import (
    parse_intent_payload,
)
from app.services.transactions_service import credit_user_from_bank
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .confirm__path__guards_service import (
    guard_amount_exact_d8,
    guard_asset_exact,
    guard_destination_exact,
)
from .shop_payment_tx_hash_lock_service import acquire_tx_hash_lock


@dataclass(frozen=True)
class ConfirmPaymentResult:
    status: str
    note: str | None = None


async def confirm_payment_intent(
    db: AsyncSession,
    *,
    intent_id: int,
    global_id: str,
    provider_tg_id: int | None,
    purpose: str,
    payload: str,
    tx_hash: str,
    amount_asset: Decimal | None,
    asset: str,
    external_amount_atomic: int | str | None = None,
    external_decimals: int | None = None,
    to_address: str,
    trusted_operation_at: datetime | None,
    server_first_seen_at: datetime | None,
    status_credited: str,
    status_paid_auto: str,
    status_error_memo: str,
    status_error_sys: str,
    status_pending_manual: str,
    item_type_efhc_package: str,
    item_type_nft_vip: str,
    now_func: Callable[[], Any],
    logger_obj: Any,
    credit_user_from_bank_fn: Callable[..., Any] | None = None,
) -> ConfirmPaymentResult:
    owner_global_id = parse_global_id(global_id)
    owner_global_id_db = global_id_to_database(owner_global_id)
    owner_global_id_text = str(owner_global_id)
    credit_fn = credit_user_from_bank_fn
    q = text(
        "\n".join(
            [
                "SELECT * FROM efhc_core.payment_intents",
                " WHERE id = :iid",
                "   AND global_id = :global_id",
                "   AND payload = :p",
                " FOR UPDATE",
            ]
        )
    )
    row = (
        (
            await db.execute(
                q,
                {
                    "iid": int(intent_id),
                    "global_id": owner_global_id_db,
                    "p": str(payload),
                },
            )
        )
        .mappings()
        .first()
    )
    if not row:
        return ConfirmPaymentResult(
            status_error_memo,
            "intent_not_found",
        )

    status_val = str(row.get("status") or "").upper()
    existing_tx_hash = str(row.get("external_tx_hash") or "").strip()
    incoming_tx_hash = str(tx_hash or "").strip()

    # P0 порядок внешнего финансового события:
    # trusted time -> 10-day barrier -> replay/idempotency -> mutation -> ledger.
    time_decision = validate_external_financial_execution(
        trusted_operation_at=trusted_operation_at,
        server_first_seen_at=server_first_seen_at,
        now=now_func(),
    )
    if not time_decision.allowed:
        return ConfirmPaymentResult(
            status_pending_manual,
            time_decision.code,
        )

    # Единственное исключение из PENDING-only settlement — точный
    # идемпотентный read-through уже подтверждённой той же транзакции.
    if status_val == "CONFIRMED" and (
        existing_tx_hash and existing_tx_hash == incoming_tx_hash
    ):
        if purpose == "shop_external":
            existing_order_status = (
                await db.execute(
                    text(
                        "SELECT status FROM efhc_core.shop_orders "
                        "WHERE global_id = :global_id "
                        "AND ((extra->>'intent_id') = :intent_id "
                        "     OR memo = :payload) "
                        "ORDER BY id DESC LIMIT 1"
                    ),
                    {
                        "global_id": owner_global_id_db,
                        "intent_id": str(int(intent_id)),
                        "payload": str(payload),
                    },
                )
            ).scalar()
            if str(existing_order_status or "") in {
                "PAID_PENDING_MANUAL",
                "APPROVED",
            }:
                return ConfirmPaymentResult(status_pending_manual, None)
            return ConfirmPaymentResult(status_paid_auto, None)
        return ConfirmPaymentResult(status_credited, None)

    # После FOR UPDATE новый settlement разрешён только живому PENDING
    # intent. CONFIRMED с другим tx_hash, CANCELED, EXPIRED и любые
    # неизвестные статусы fail-closed и не могут начислять EFHC.
    if status_val != "PENDING":
        return ConfirmPaymentResult(
            status_pending_manual,
            "INTENT_NOT_PENDING",
        )

    expires_at = row.get("expires_at")
    now_value = time_decision.checked_at
    payment_time = time_decision.trusted_operation_at
    if expires_at is None or payment_time is None:
        return ConfirmPaymentResult(
            status_pending_manual,
            "INTENT_EXPIRY_MISSING",
        )
    try:
        is_expired = bool(expires_at <= payment_time)
    except TypeError:
        # Compatibility с SQLite fixtures: ISO-текст сравниваем через
        # нормализованное строковое представление, production PostgreSQL
        # возвращает timezone-aware datetime.
        is_expired = str(expires_at) <= str(payment_time)
    if is_expired:
        return ConfirmPaymentResult(
            status_pending_manual,
            "INTENT_EXPIRED",
        )

    asset_expected = str(row.get("asset") or "TON").upper()
    asset_guard = guard_asset_exact(
        asset=str(asset or "TON"),
        expected_asset=asset_expected,
    )
    if not asset_guard.ok:
        return ConfirmPaymentResult(
            status_error_sys,
            asset_guard.reason,
        )

    to_guard = guard_destination_exact(
        to_address=str(to_address or ""),
        expected_to=str(row.get("to_address") or ""),
    )
    if not to_guard.ok:
        return ConfirmPaymentResult(status_error_sys, to_guard.reason)

    parsed_payload = parse_intent_payload(str(row.get("payload") or ""))
    if parsed_payload and int(parsed_payload.get("payload_version") or 1) >= 2:
        if external_amount_atomic is None:
            return ConfirmPaymentResult(
                status_error_sys, "EXTERNAL_AMOUNT_ATOMIC_REQUIRED"
            )
        try:
            incoming_external = external_amount_from_atomic(
                asset_expected, external_amount_atomic, require_positive=True
            )
        except ValueError as exc:
            return ConfirmPaymentResult(status_error_sys, str(exc))
        expected_atomic = int(parsed_payload.get("external_amount_atomic") or -1)
        expected_decimals = int(parsed_payload.get("external_decimals") or -1)
        if (
            str(parsed_payload.get("asset") or "").upper() != asset_expected
            or incoming_external.atomic != expected_atomic
            or incoming_external.decimals != expected_decimals
            or (
                external_decimals is not None
                and int(external_decimals) != expected_decimals
            )
        ):
            return ConfirmPaymentResult(
                status_error_sys, "EXTERNAL_AMOUNT_ATOMIC_MISMATCH"
            )
    else:
        # Legacy v1 compatibility only. New EFHC2 intents never use D8 for
        # TON/USDT settlement authority.
        if amount_asset is None:
            return ConfirmPaymentResult(status_error_sys, "AMOUNT_REQUIRED")
        amount_guard = guard_amount_exact_d8(
            amount_asset=amount_asset,
            expected_d8=row.get("amount_asset_d8") or 0,
        )
        if not amount_guard.ok:
            return ConfirmPaymentResult(
                status_error_sys,
                amount_guard.reason,
            )

    q_tx = text(
        "\n".join(
            [
                "SELECT id FROM efhc_core.payment_intents",
                " WHERE external_tx_hash = :h",
                "   AND id <> :iid",
                " LIMIT 1",
            ]
        )
    )
    tx_row = (
        await db.execute(
            q_tx,
            {"h": str(tx_hash), "iid": int(intent_id)},
        )
    ).first()
    if tx_row:
        return ConfirmPaymentResult(
            status_error_sys,
            "TX_HASH_ALREADY_USED",
        )

    q_upd = text(
        "\n".join(
            [
                "UPDATE efhc_core.payment_intents",
                "   SET status = 'CONFIRMED',",
                "       external_tx_hash = :h,",
                "       updated_at = :now",
                " WHERE id = :iid",
            ]
        )
    )

    if purpose == "deposit_efhc":
        lock_ok = await acquire_tx_hash_lock(
            db,
            tx_hash=str(tx_hash),
            purpose=str(purpose),
            intent_id=int(intent_id),
            global_id=owner_global_id_text,
            trusted_operation_at=time_decision.trusted_operation_at,
            server_first_seen_at=time_decision.server_first_seen_at,
            order_id=None,
        )
        if not lock_ok:
            logger_obj.error(
                "deposit confirm blocked: tx_hash lock conflict "
                "(intent_id=%s global_id=%s tx_hash=%r)",
                intent_id,
                global_id,
                tx_hash,
            )
            return ConfirmPaymentResult(
                status_error_sys,
                "TX_HASH_LOCK_CONFLICT",
            )

        if status_val != "CONFIRMED":
            await db.execute(
                q_upd,
                {
                    "iid": int(intent_id),
                    "h": str(tx_hash),
                    "now": now_func(),
                },
            )
        efhc_amt = d8(row.get("efhc_amount_d8") or 0)
        credit_meta = {
            "domain": "efhc_external_deposit",
            "intent_id": int(intent_id),
            "tx_hash": str(tx_hash),
            "external_settlement": "received",
            "settlement_status": "confirmed",
            "bank_counterparty": "BANK_EFHC",
        }
        credit_idempotency_key = (
            f"intent:{intent_id}:confirm:{str(tx_hash)}"
        )
        if credit_fn is None:
            # Единственная явная DB-граница canonical transactions service.
            await credit_user_from_bank(
                db,
                global_id=owner_global_id_db,
                amount_efhc=efhc_amt,
                reason="deposit_efhc_confirm",
                idempotency_key=credit_idempotency_key,
                meta=credit_meta,
            )
        else:
            # Compatibility/dependency seam получает только внешний string ID.
            await credit_fn(
                db,
                global_id=owner_global_id_text,
                amount_efhc=efhc_amt,
                reason="deposit_efhc_confirm",
                idempotency_key=credit_idempotency_key,
                meta=credit_meta,
            )
        await db.commit()
        return ConfirmPaymentResult(status_credited, None)

    if purpose == "shop_external":
        q_order = text(
            "\n".join(
                [
                    "SELECT o.id AS order_id,",
                    "       o.type AS order_type,",
                    "       o.quantity_efhc AS quantity_efhc,",
                    "       o.idempotency_key AS idempotency_key,",
                    "       o.extra AS extra_json",
                    "  FROM efhc_core.shop_orders o",
                    " WHERE o.global_id = :global_id",
                    "   AND o.memo = :m",
                    "   AND o.status = 'PENDING'",
                    " ORDER BY o.id ASC",
                    " LIMIT 1",
                ]
            )
        )
        o = (
            (
                await db.execute(
                    q_order,
                    {"global_id": owner_global_id_db, "m": str(payload)},
                )
            )
            .mappings()
            .first()
        )
        if not o:
            logger_obj.warning(
                "shop_external confirm blocked: "
                "pending order not found "
                "(intent_id=%s global_id=%s payload=%r tx_hash=%r)",
                intent_id,
                global_id,
                payload,
                tx_hash,
            )
            return ConfirmPaymentResult(
                status_pending_manual,
                "PENDING_ORDER_NOT_FOUND",
            )

        extra_json = o.get("extra_json") or {}
        legacy_order_shape = not bool(extra_json)

        async def _set_order_error(msg: str) -> None:
            await db.execute(
                text(
                    "UPDATE efhc_core.shop_orders "
                    "SET payment_error_log = :msg, updated_at = NOW() "
                    "WHERE id = :oid"
                ),
                {"oid": int(o["order_id"]), "msg": str(msg)},
            )

        extra_sku = str(extra_json.get("sku") or "").strip()
        extra_item_type = str(extra_json.get("item_type") or "").strip()
        extra_method = (
            str(extra_json.get("payment_method") or "").strip().upper()
        )
        extra_canonical_memo = str(
            extra_json.get("canonical_memo") or ""
        ).strip()
        extra_intent_payload = str(
            extra_json.get("intent_payload") or ""
        ).strip()
        extra_owner_global = str(
            extra_json.get("payment_owner_global_id") or ""
        ).strip()
        extra_owner_tg = str(
            extra_json.get("payment_owner_tg_id") or ""
        ).strip()
        if (
            not extra_sku
            or not extra_item_type
            or not extra_canonical_memo
            or not extra_intent_payload
            or not (extra_owner_global or extra_owner_tg)
        ):
            if not legacy_order_shape:
                logger_obj.warning(
                    "shop_external confirm blocked: "
                    "order extra snapshot is incomplete "
                    "(intent_id=%s order_id=%s)",
                    intent_id,
                    int(o["order_id"]),
                )
                await _set_order_error(
                    "ORDER_EXTRA_SNAPSHOT_INCOMPLETE"
                )
                return ConfirmPaymentResult(
                    status_pending_manual,
                    "ORDER_EXTRA_SNAPSHOT_INCOMPLETE",
                )
            extra_intent_payload = str(payload)
            extra_owner_global = owner_global_id_text
            extra_owner_tg = (
                str(int(provider_tg_id))
                if provider_tg_id is not None
                else ""
            )
            if str(o.get("order_type") or "") == "EFHC":
                extra_item_type = str(item_type_efhc_package)
                qty_raw = o.get("quantity_efhc")
                qty_int = int(Decimal(str(qty_raw or "0")))
                extra_canonical_memo = (
                    f"SKU:EFHC|Q:{qty_int}|G:{owner_global_id_text}"
                )
            elif str(o.get("order_type") or "") == "NFT":
                extra_item_type = str(item_type_nft_vip)
                extra_canonical_memo = (
                    f"SKU:NFT_VIP|Q:1|G:{owner_global_id_text}"
                )

        if extra_intent_payload != str(payload):
            logger_obj.warning(
                "shop_external confirm blocked: "
                "intent payload snapshot mismatch "
                "(intent_id=%s order_id=%s)",
                intent_id,
                int(o["order_id"]),
            )
            await _set_order_error("INTENT_PAYLOAD_SNAPSHOT_MISMATCH")
            return ConfirmPaymentResult(
                status_pending_manual,
                "INTENT_PAYLOAD_SNAPSHOT_MISMATCH",
            )

        owner_matches = extra_owner_global == owner_global_id_text
        historical_provider_owner_only = bool(
            not extra_owner_global and extra_owner_tg
        )
        if (
            not owner_matches
            and historical_provider_owner_only
            and provider_tg_id is not None
        ):
            owner_matches = extra_owner_tg == str(int(provider_tg_id))
        if not owner_matches:
            logger_obj.warning(
                "shop_external confirm blocked: payment owner mismatch "
                "(intent_id=%s order_id=%s)",
                intent_id,
                int(o["order_id"]),
            )
            await _set_order_error("PAYMENT_OWNER_MISMATCH")
            return ConfirmPaymentResult(
                status_pending_manual,
                "PAYMENT_OWNER_MISMATCH",
            )

        if extra_item_type == item_type_efhc_package:
            intent_efhc_amount = d8(row.get("efhc_amount_d8") or 0)
            order_efhc_amount = d8(o.get("quantity_efhc") or 0)
            if (
                intent_efhc_amount > d8("0")
                and intent_efhc_amount != order_efhc_amount
            ):
                await _set_order_error("EFHC_AMOUNT_SNAPSHOT_MISMATCH")
                return ConfirmPaymentResult(
                    status_pending_manual,
                    "EFHC_AMOUNT_SNAPSHOT_MISMATCH",
                )

        selected_vip_item_row = None
        selected_vip_item_extra: dict[str, Any] | None = None
        if extra_item_type == "NFT_VIP_NUMBER":
            selected_vip_item_row = (
                (
                    await db.execute(
                        text(
                            "SELECT id, extra FROM efhc_core.shop_items "
                            "WHERE sku = :sku FOR UPDATE"
                        ),
                        {"sku": extra_sku},
                    )
                )
                .mappings()
                .first()
            )
            if selected_vip_item_row is None:
                await _set_order_error("VIP_NUMBER_ITEM_NOT_FOUND")
                return ConfirmPaymentResult(
                    status_pending_manual,
                    "VIP_NUMBER_ITEM_NOT_FOUND",
                )
            raw_item_extra = selected_vip_item_row.get("extra") or {}
            if not isinstance(raw_item_extra, dict):
                await _set_order_error("VIP_NUMBER_STATE_INVALID")
                return ConfirmPaymentResult(
                    status_pending_manual,
                    "VIP_NUMBER_STATE_INVALID",
                )
            selected_vip_item_extra = dict(raw_item_extra)
            reservation = selected_vip_item_extra.get("vip_number_reservation")
            if not isinstance(reservation, dict):
                await _set_order_error("VIP_NUMBER_RESERVATION_MISSING")
                return ConfirmPaymentResult(
                    status_pending_manual,
                    "VIP_NUMBER_RESERVATION_MISSING",
                )
            reservation_expires_raw = str(reservation.get("expires_at") or "")
            try:
                reservation_expires = datetime.fromisoformat(
                    reservation_expires_raw.replace("Z", "+00:00")
                )
            except ValueError:
                reservation_expires = None
            reservation_ok = bool(
                reservation_expires is not None
                and reservation_expires.tzinfo is not None
                and reservation_expires > payment_time
                and str(reservation.get("global_id") or "")
                == owner_global_id_text
                and int(reservation.get("order_id") or 0)
                == int(o["order_id"])
                and int(reservation.get("intent_id") or 0)
                == int(intent_id)
                and str(reservation.get("idempotency_key") or "")
                == str(o.get("idempotency_key") or "")
            )
            if not reservation_ok:
                await _set_order_error("VIP_NUMBER_RESERVATION_MISMATCH")
                return ConfirmPaymentResult(
                    status_pending_manual,
                    "VIP_NUMBER_RESERVATION_MISMATCH",
                )
            preexisting_claim = selected_vip_item_extra.get("vip_number_claim")
            if isinstance(preexisting_claim, dict):
                same_preexisting_claim = (
                    str(preexisting_claim.get("global_id") or "")
                    == owner_global_id_text
                    and int(preexisting_claim.get("order_id") or 0)
                    == int(o["order_id"])
                    and int(preexisting_claim.get("intent_id") or 0)
                    == int(intent_id)
                )
                if not same_preexisting_claim:
                    await _set_order_error("VIP_NUMBER_CLAIM_CONFLICT")
                    return ConfirmPaymentResult(
                        status_pending_manual,
                        "VIP_NUMBER_CLAIM_CONFLICT",
                    )

        expected_canonical_memos: set[str] = set()
        if extra_item_type == item_type_efhc_package:
            qty_raw = o.get("quantity_efhc")
            qty_int = int(Decimal(str(qty_raw or "0")))
            expected_canonical_memos.add(
                f"SKU:EFHC|Q:{qty_int}|G:{owner_global_id_text}"
            )
            expected_canonical_memos.add(
                f"SKU:EFHC|Q:{qty_int}|GID:{owner_global_id_text}"
            )
            if provider_tg_id is not None:
                expected_canonical_memos.add(
                    f"SKU:EFHC|Q:{qty_int}|TG:{int(provider_tg_id)}"
                )
        elif extra_item_type in {
            item_type_nft_vip,
            "NFT_VIP_SELECTED_PRICE",
            "NFT_VIP_NUMBER",
        }:
            expected_canonical_memos.add(
                f"SKU:NFT_VIP|Q:1|G:{owner_global_id_text}"
            )
            expected_canonical_memos.add(
                f"SKU:NFT_VIP|Q:1|GID:{owner_global_id_text}"
            )
            if provider_tg_id is not None:
                expected_canonical_memos.add(
                    f"SKU:NFT_VIP|Q:1|TG:{int(provider_tg_id)}"
                )

        if (
            expected_canonical_memos
            and extra_canonical_memo not in expected_canonical_memos
        ):
            logger_obj.warning(
                "shop_external confirm blocked: "
                "canonical memo mismatch "
                "(intent_id=%s order_id=%s got=%r expected=%r)",
                intent_id,
                int(o["order_id"]),
                extra_canonical_memo,
                sorted(expected_canonical_memos),
            )
            await _set_order_error("CANONICAL_MEMO_MISMATCH")
            return ConfirmPaymentResult(
                status_pending_manual,
                "CANONICAL_MEMO_MISMATCH",
            )

        if extra_method and extra_method != asset_expected:
            logger_obj.warning(
                "shop_external confirm blocked: "
                "payment method mismatch "
                "(intent_id=%s order_id=%s got=%r expected=%r)",
                intent_id,
                int(o["order_id"]),
                extra_method,
                asset_expected,
            )
            await _set_order_error("PAYMENT_METHOD_MISMATCH")
            return ConfirmPaymentResult(
                status_pending_manual,
                "PAYMENT_METHOD_MISMATCH",
            )

        lock_ok = await acquire_tx_hash_lock(
            db,
            tx_hash=str(tx_hash),
            purpose=str(purpose),
            intent_id=int(intent_id),
            global_id=owner_global_id_text,
            trusted_operation_at=time_decision.trusted_operation_at,
            server_first_seen_at=time_decision.server_first_seen_at,
            order_id=int(o["order_id"]),
        )
        if not lock_ok:
            logger_obj.error(
                "shop_external confirm blocked: tx_hash lock conflict "
                "(intent_id=%s order_id=%s global_id=%s tx_hash=%r)",
                intent_id,
                int(o["order_id"]),
                global_id,
                tx_hash,
            )
            await _set_order_error("confirm__path__guard_failed")
            return ConfirmPaymentResult(
                status_error_sys,
                "confirm__path__guard_failed",
            )

        row_paid = (
            (
                await db.execute(
                    text(
                        "UPDATE efhc_core.shop_orders "
                        "SET status = CASE "
                        "WHEN type = 'NFT' THEN 'PAID_PENDING_MANUAL' "
                        "ELSE 'PAID_AUTO' END, "
                        "tx_hash = :h, "
                        "payment_error_log = NULL, "
                        "paid_at = COALESCE(paid_at, NOW()), "
                        "updated_at = NOW() "
                        "WHERE id = :oid "
                        "AND status = 'PENDING' "
                        "RETURNING type AS order_type, "
                        "status AS order_status, "
                        "quantity_efhc AS quantity_efhc"
                    ),
                    {
                        "h": str(tx_hash),
                        "oid": int(o["order_id"]),
                    },
                )
            )
            .mappings()
            .first()
        )
        if not row_paid:
            logger_obj.warning(
                "shop_external confirm blocked: "
                "order update not applied "
                "(intent_id=%s order_id=%s tx_hash=%r)",
                intent_id,
                int(o["order_id"]),
                tx_hash,
            )
            await _set_order_error("ORDER_UPDATE_NOT_APPLIED")
            return ConfirmPaymentResult(
                status_pending_manual,
                "ORDER_UPDATE_NOT_APPLIED",
            )

        if (
            selected_vip_item_row is not None
            and selected_vip_item_extra is not None
        ):
            claim = selected_vip_item_extra.get("vip_number_claim")
            if isinstance(claim, dict):
                same_claim = (
                    str(claim.get("global_id") or "") == owner_global_id_text
                    and int(claim.get("order_id") or 0) == int(o["order_id"])
                    and int(claim.get("intent_id") or 0) == int(intent_id)
                )
                if not same_claim:
                    await _set_order_error("VIP_NUMBER_CLAIM_CONFLICT")
                    return ConfirmPaymentResult(
                        status_pending_manual,
                        "VIP_NUMBER_CLAIM_CONFLICT",
                    )
            else:
                selected_vip_item_extra["vip_number_claim"] = {
                    "global_id": owner_global_id_text,
                    "idempotency_key": str(o.get("idempotency_key") or ""),
                    "order_id": int(o["order_id"]),
                    "intent_id": int(intent_id),
                    "claimed_at": now_value.isoformat(),
                }
                selected_vip_item_extra["status"] = "sold"
                await db.execute(
                    text(
                        "UPDATE efhc_core.shop_items "
                        "SET extra = CAST(:extra AS jsonb), updated_at = :now "
                        "WHERE id = :item_id"
                    ),
                    {
                        "extra": json.dumps(selected_vip_item_extra),
                        "now": now_value,
                        "item_id": int(selected_vip_item_row["id"]),
                    },
                )

        if status_val != "CONFIRMED":
            await db.execute(
                q_upd,
                {
                    "iid": int(intent_id),
                    "h": str(tx_hash),
                    "now": now_func(),
                },
            )

        order_type = str(row_paid.get("order_type") or "")
        quantity_efhc = row_paid.get("quantity_efhc")
        if order_type == "EFHC" and quantity_efhc is not None:
            qty = d8(Decimal(str(quantity_efhc)))
            if qty > d8("0"):
                if credit_fn is None:
                    # Канонический writer принимает физический BIGINT только
                    # на явной DB-границе; внешний payment owner остаётся
                    # десятизначной строкой global_id.
                    await credit_user_from_bank(
                        db,
                        global_id=owner_global_id_db,
                        amount_efhc=qty,
                        reason="shop_external_efhc_confirm",
                        idempotency_key=f"intent:{intent_id}:shop_credit",
                    )
                else:
                    # Compatibility/dependency seam получает только внешний
                    # десятизначный global_id и не становится вторым writer.
                    await credit_fn(
                        db,
                        global_id=owner_global_id_text,
                        amount_efhc=qty,
                        reason="shop_external_efhc_confirm",
                        idempotency_key=f"intent:{intent_id}:shop_credit",
                    )
        await db.commit()
        try:
            from .shop_order_notifications_service import (
                dispatch_shop_order_notifications,
            )

            await dispatch_shop_order_notifications(db, limit=25)
            await db.commit()
        except Exception as exc:
            logger_obj.warning(
                "shop_external notification dispatch skipped "
                "(intent_id=%s order_id=%s err=%s)",
                intent_id,
                o["order_id"],
                exc,
            )
        return ConfirmPaymentResult(
            status_pending_manual if order_type == "NFT" else status_paid_auto,
            None,
        )

    await db.commit()
    return ConfirmPaymentResult(
        status_error_sys,
        "unsupported_confirm_purpose",
    )
