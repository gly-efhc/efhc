# backend/app/services/payment_intents_service.py
# =====================================================================
# Назначение:
# Технический слой Payment Intents для on-chain оплат (TonConnect).
# Используется для:
# • deposit_efhc (Пополнить EFHC)
# • shop_external (внешний Shop за TON/USDT)
#
# Канон / инварианты:
# • tg_id — только из Telegram initData (routes/deps).
# • Внутренний EFHC — D8; TON/USDT — asset-native integer atomic units.
# • Идемпотентность: UNIQUE(global_id,purpose,idempotency_key).
# • Новые payload: EFHC2:<purpose>:<intent_id>:G<global_id>:<asset>:<atomic>.
# • Legacy EFHC:<purpose>:<intent_id>:<global_id> читается только совместимо.
# • Статусы: PENDING|CONFIRMED|EXPIRED|CANCELED.
# • SENT больше не создаётся сервером; старые сохранённые записи
#   могут читаться как историческое состояние до их завершения.
# =====================================================================

from __future__ import annotations

import base64
from collections.abc import Mapping
from datetime import timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Any, cast

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.deps import d8
from app.domain.finance.external_amounts import (
    external_amount_from_atomic,
    external_amount_from_display,
)
from app.identity.financial_write_owner import (
    FinancialWriteOwner,
    resolve_and_lock_financial_write_owner,
)
from app.identity.types import (
    global_id_from_database,
    global_id_to_database,
    parse_global_id,
)
from app.lib.time import utcnow
from app.services.intent_payload_parsing_service import (
    parse_intent_payload,
)
from app.services.shop_prepayment_store import require_no_active_shop_preparation
from app.services.transactions_service import (
    IdempotencyPayloadConflictError,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
S = get_settings()
SCHEMA = getattr(S, "DB_SCHEMA_CORE", "efhc_core")
if str(SCHEMA) != "efhc_core":
    raise RuntimeError("payment_intents_service requires efhc_core")

PI_TABLE = "efhc_core.payment_intents"
PI_SEQUENCE_OWNER = PI_TABLE

"""Postgres-only."""


STATUS_PENDING = "PENDING"
PENDING_INTENT_LIMIT = 5
STATUS_CONFIRMED = "CONFIRMED"
STATUS_EXPIRED = "EXPIRED"
STATUS_CANCELED = "CANCELED"


STATUS_ERROR_RETRY = "error_retry"
STATUS_ERROR_NETWORK_RETRY = "error_network_retry"
STATUS_PENDING_MANUAL = "pending_manual"
STATUS_PENDING_MAPPING = "parsed_pending_mapping"
STATUS_RECEIVED = "received"
STATUS_PARSED = "parsed"


def _global_id_db(global_id: str) -> int:
    """Преобразовать внешний global_id в физическое значение только у БД."""
    return cast(int, global_id_to_database(parse_global_id(global_id)))



def _canonical_return_path(*, product_state: str) -> str:
    if product_state == "active":
        return "browser_shop"
    if product_state == "pending_external":
        return "web_profile"
    return "web_profile"


def _canonical_next_action(
    *,
    product_state: str,
    purpose: str,
) -> str:
    if product_state == "active":
        return "resume_browser_shop"
    if product_state == "pending_external":
        return "wait_network"
    if product_state == "manual_review":
        return "wait_manual_review"
    if product_state == "terminal_success":
        return (
            "back_to_telegram"
            if purpose == "deposit_efhc"
            else "open_web_profile"
        )
    if product_state in {"terminal_failed", "expired"}:
        return "create_new_intent"
    return "wait_processing"


def _wallet_readiness_payload(
    *,
    require_handoff: bool,
    handoff_configured: bool,
    wallet_linked: bool,
    wallet_sync_required: bool,
    has_active_intent: bool,
    next_action: str,
) -> dict[str, Any]:
    if require_handoff:
        return {
            "wallet_ready": False,
            "wallet_blocked": True,
            "action_allowed": False,
            "action_denied": True,
            "readiness_state": "telegram_handoff_required",
            "primary_cta": "open_telegram_handoff",
        }
    if not handoff_configured:
        return {
            "wallet_ready": wallet_linked,
            "wallet_blocked": True,
            "action_allowed": False,
            "action_denied": True,
            "readiness_state": "external_flow_missing",
            "primary_cta": "unavailable",
        }
    if wallet_sync_required or not wallet_linked:
        return {
            "wallet_ready": False,
            "wallet_blocked": True,
            "action_allowed": False,
            "action_denied": True,
            "readiness_state": "wallet_sync_required",
            "primary_cta": "sync_wallet",
        }
    if has_active_intent:
        return {
            "wallet_ready": True,
            "wallet_blocked": False,
            "action_allowed": True,
            "action_denied": False,
            "readiness_state": "resume_active_intent",
            "primary_cta": next_action,
        }
    return {
        "wallet_ready": True,
        "wallet_blocked": False,
        "action_allowed": True,
        "action_denied": False,
        "readiness_state": "ready",
        "primary_cta": next_action,
    }


def _is_expired_now(expires_at: Any) -> bool:
    try:
        if not expires_at:
            return False
        return bool(expires_at < (utcnow() - timedelta(seconds=1)))
    except Exception:
        return False


def _build_intent_flow_truth(
    *,
    purpose: str,
    intent_status: str,
    expires_at: Any,
    external_tx_hash: str | None,
    order: Mapping[str, Any] | None,
    inbox: Mapping[str, Any] | None,
) -> dict[str, Any]:
    status = str(intent_status or "").upper()
    watcher_status = (
        str(inbox.get("status") or "") if inbox is not None else None
    )
    watcher_last_error = (
        str(inbox.get("last_error") or "")
        if inbox is not None and inbox.get("last_error")
        else None
    )
    watcher_tx_hash = (
        str(inbox.get("tx_hash") or "")
        if inbox is not None and inbox.get("tx_hash")
        else external_tx_hash
    )
    order_id = (
        int(order["id"])
        if order is not None and order.get("id") is not None
        else None
    )
    order_status = (
        str(order.get("status") or "")
        if order is not None and order.get("status") is not None
        else None
    )
    payment_error_log = (
        str(order.get("payment_error_log") or "")
        if order is not None and order.get("payment_error_log")
        else None
    )

    if status == STATUS_CONFIRMED:
        if purpose == "deposit_efhc":
            return {
                "lifecycle_stage": "credited",
                "product_state": "terminal_success",
                "lifecycle_terminal": True,
                "next_step": "back_to_telegram",
                "next_action": _canonical_next_action(
                    product_state="terminal_success",
                    purpose=purpose,
                ),
                "return_path": _canonical_return_path(
                    product_state="terminal_success",
                ),
                "canonical_center": "web_profile",
                "message_key": "payment.flow.confirmed_deposit",
                "watcher_status": watcher_status,
                "watcher_tx_hash": watcher_tx_hash,
                "watcher_last_error": watcher_last_error,
                "order_id": order_id,
                "order_status": order_status,
                "payment_error_log": payment_error_log,
            }
        if order_status in {"PAID_AUTO", "APPROVED"}:
            return {
                "lifecycle_stage": "credited",
                "product_state": "terminal_success",
                "lifecycle_terminal": True,
                "next_step": "back_to_telegram",
                "next_action": _canonical_next_action(
                    product_state="terminal_success",
                    purpose=purpose,
                ),
                "return_path": _canonical_return_path(
                    product_state="terminal_success",
                ),
                "canonical_center": "web_profile",
                "message_key": "payment.flow.confirmed_order",
                "watcher_status": watcher_status,
                "watcher_tx_hash": watcher_tx_hash,
                "watcher_last_error": watcher_last_error,
                "order_id": order_id,
                "order_status": order_status,
                "payment_error_log": payment_error_log,
            }
        if order_status in {"PAID_PENDING_MANUAL", "PENDING"}:
            return {
                "lifecycle_stage": "manual_review",
                "product_state": "manual_review",
                "lifecycle_terminal": False,
                "next_step": "wait_manual_review",
                "next_action": _canonical_next_action(
                    product_state="manual_review",
                    purpose=purpose,
                ),
                "return_path": _canonical_return_path(
                    product_state="manual_review",
                ),
                "canonical_center": "web_profile",
                "message_key": "payment.flow.order_manual_review",
                "watcher_status": watcher_status,
                "watcher_tx_hash": watcher_tx_hash,
                "watcher_last_error": watcher_last_error,
                "order_id": order_id,
                "order_status": order_status,
                "payment_error_log": payment_error_log,
            }

    if status == STATUS_EXPIRED or _is_expired_now(expires_at):
        return {
            "lifecycle_stage": "expired",
            "product_state": "expired",
            "lifecycle_terminal": True,
            "next_step": "create_new_intent",
            "next_action": _canonical_next_action(
                product_state="expired",
                purpose=purpose,
            ),
            "return_path": _canonical_return_path(
                product_state="expired",
            ),
            "canonical_center": "web_profile",
            "message_key": "payment.flow.expired",
            "watcher_status": watcher_status,
            "watcher_tx_hash": watcher_tx_hash,
            "watcher_last_error": watcher_last_error,
            "order_id": order_id,
            "order_status": order_status,
            "payment_error_log": payment_error_log,
        }

    if status == STATUS_CANCELED:
        return {
            "lifecycle_stage": "canceled",
            "product_state": "terminal_failed",
            "lifecycle_terminal": True,
            "next_step": "create_new_intent",
            "next_action": _canonical_next_action(
                product_state="terminal_failed",
                purpose=purpose,
            ),
            "return_path": _canonical_return_path(
                product_state="terminal_failed",
            ),
            "canonical_center": "web_profile",
            "message_key": "payment.flow.canceled",
            "watcher_status": watcher_status,
            "watcher_tx_hash": watcher_tx_hash,
            "watcher_last_error": watcher_last_error,
            "order_id": order_id,
            "order_status": order_status,
            "payment_error_log": payment_error_log,
        }

    if watcher_status in {STATUS_RECEIVED, STATUS_PARSED}:
        return {
            "lifecycle_stage": "network_seen",
            "product_state": "pending_external",
            "lifecycle_terminal": False,
            "next_step": "wait_network",
            "next_action": _canonical_next_action(
                product_state="pending_external",
                purpose=purpose,
            ),
            "return_path": _canonical_return_path(
                product_state="pending_external",
            ),
            "canonical_center": "web_profile",
            "message_key": "payment.flow.network_processing",
            "watcher_status": watcher_status,
            "watcher_tx_hash": watcher_tx_hash,
            "watcher_last_error": watcher_last_error,
            "order_id": order_id,
            "order_status": order_status,
            "payment_error_log": payment_error_log,
        }

    if watcher_status in {
        STATUS_ERROR_RETRY,
        STATUS_ERROR_NETWORK_RETRY,
    }:
        return {
            "lifecycle_stage": "network_seen",
            "product_state": "pending_external",
            "lifecycle_terminal": False,
            "next_step": "wait_network",
            "next_action": _canonical_next_action(
                product_state="pending_external",
                purpose=purpose,
            ),
            "return_path": _canonical_return_path(
                product_state="pending_external",
            ),
            "canonical_center": "web_profile",
            "message_key": "payment.flow.retrying",
            "watcher_status": watcher_status,
            "watcher_tx_hash": watcher_tx_hash,
            "watcher_last_error": watcher_last_error,
            "order_id": order_id,
            "order_status": order_status,
            "payment_error_log": payment_error_log,
        }

    if watcher_status in {
        STATUS_PENDING_MANUAL,
        STATUS_PENDING_MAPPING,
    }:
        return {
            "lifecycle_stage": "manual_review",
            "product_state": "manual_review",
            "lifecycle_terminal": False,
            "next_step": "wait_manual_review",
            "next_action": _canonical_next_action(
                product_state="manual_review",
                purpose=purpose,
            ),
            "return_path": _canonical_return_path(
                product_state="manual_review",
            ),
            "canonical_center": "web_profile",
            "message_key": "payment.flow.manual_review",
            "watcher_status": watcher_status,
            "watcher_tx_hash": watcher_tx_hash,
            "watcher_last_error": watcher_last_error,
            "order_id": order_id,
            "order_status": order_status,
            "payment_error_log": payment_error_log,
        }

    if order_status in {"REJECTED", "CANCELLED"}:
        return {
            "lifecycle_stage": "failed",
            "product_state": "terminal_failed",
            "lifecycle_terminal": True,
            "next_step": "create_new_intent",
            "next_action": _canonical_next_action(
                product_state="terminal_failed",
                purpose=purpose,
            ),
            "return_path": _canonical_return_path(
                product_state="terminal_failed",
            ),
            "canonical_center": "web_profile",
            "message_key": "payment.flow.failed",
            "watcher_status": watcher_status,
            "watcher_tx_hash": watcher_tx_hash,
            "watcher_last_error": watcher_last_error,
            "order_id": order_id,
            "order_status": order_status,
            "payment_error_log": payment_error_log,
        }

    if external_tx_hash:
        return {
            "lifecycle_stage": "network_seen",
            "product_state": "pending_external",
            "lifecycle_terminal": False,
            "next_step": "wait_network",
            "next_action": _canonical_next_action(
                product_state="pending_external",
                purpose=purpose,
            ),
            "return_path": _canonical_return_path(
                product_state="pending_external",
            ),
            "canonical_center": "web_profile",
            "message_key": "payment.flow.external_detected",
            "watcher_status": watcher_status,
            "watcher_tx_hash": watcher_tx_hash,
            "watcher_last_error": watcher_last_error,
            "order_id": order_id,
            "order_status": order_status,
            "payment_error_log": payment_error_log,
        }

    return {
        "lifecycle_stage": "initiated",
        "product_state": "active",
        "lifecycle_terminal": False,
        "next_step": "pay_or_wait",
        "next_action": _canonical_next_action(
            product_state="active",
            purpose=purpose,
        ),
        "return_path": _canonical_return_path(
            product_state="active",
        ),
        "canonical_center": "web_profile",
        "message_key": "payment.flow.active",
        "watcher_status": watcher_status,
        "watcher_tx_hash": watcher_tx_hash,
        "watcher_last_error": watcher_last_error,
        "order_id": order_id,
        "order_status": order_status,
        "payment_error_log": payment_error_log,
    }


def _ttl_minutes() -> int:
    val = getattr(S, "PAYMENT_INTENT_TTL_MIN", 15)
    try:
        n = int(val or 15)
    except Exception:
        n = 15
    return max(5, min(60, n))


def _ton_to_nano_from_d8(amount_d8: Decimal) -> str:
    """Compatibility seam: external TON display → exact nanotons; EFHC d8 не используется."""
    return str(
        external_amount_from_display(
            "TON", amount_d8, require_positive=False
        ).atomic
    )


def _usdt_to_units_from_d8(amount_d8: Decimal) -> str:
    """Compatibility seam: external USDT display → exact 10^6 units; EFHC d8 не используется."""
    return str(
        external_amount_from_display(
            "USDT", amount_d8, require_positive=False
        ).atomic
    )


def get_usdt_checkout_mode() -> str:
    """Server-truth runtime mode for USDT checkout."""
    return "tep74_live"


async def _assert_pending_intent_limit(
    db: AsyncSession,
    *,
    global_id: str,
    purpose: str,
) -> None:
    result = await db.execute(
        text(
            "SELECT count(*) FROM efhc_core.payment_intents "
            "WHERE global_id = :global_id AND purpose = :purpose "
            "AND status = 'PENDING' AND expires_at > NOW()"
        ),
        {"global_id": _global_id_db(global_id), "purpose": str(purpose)},
    )
    pending_limit = 1 if str(purpose) == "shop_external" else PENDING_INTENT_LIMIT
    if int(result.scalar() or 0) >= int(pending_limit):
        raise ValueError("PENDING_INTENT_LIMIT_REACHED")



def _b64_text(s: str) -> str:
    """Base64-encode text for TonConnect payload field."""
    raw = (s or "").encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


_PI_SEQUENCE_EXPR = "pg_get_serial_sequence(:pi_table, 'id')"


def _legacy_external_amount_d8(value: Decimal) -> Decimal:
    """Frozen NUMERIC(38,8) compatibility projection; not v2 settlement authority."""
    return Decimal(str(value)).quantize(
        Decimal("0.00000001"), rounding=ROUND_DOWN
    )


def build_payload(
    *,
    purpose: str,
    intent_id: int,
    global_id: str,
    asset: str | None = None,
    external_amount_atomic: int | str | None = None,
) -> str:
    """Build payload; new external intents use EFHC2 with immutable atomic snapshot."""
    owner_token = f"G{global_id}"
    if asset is not None and external_amount_atomic is not None:
        external = external_amount_from_atomic(
            str(asset), external_amount_atomic, require_positive=True
        )
        return (
            f"EFHC2:{purpose}:{int(intent_id)}:{owner_token}:"
            f"{external.asset.value}:{external.atomic}"
        )
    return f"EFHC:{purpose}:{int(intent_id)}:{owner_token}"


def build_transport_meta(*, asset: str, payload: str) -> dict[str, Any]:
    asset_u = str(asset or "TON").upper()
    if asset_u == "TON":
        return {
            "tonconnect_transport_kind": "native_ton",
            "jetton_master_address": None,
            "jetton_decimals": None,
            "forward_payload_text": str(payload),
            "fee_message_ton_amount": None,
            "forward_ton_amount": None,
            "recipient_strategy": None,
            "usdt_checkout_mode": get_usdt_checkout_mode(),
        }

    if asset_u == "USDT":
        return {
            "tonconnect_transport_kind": "jetton_transfer",
            "jetton_master_address": (
                str(getattr(S, "USDT_JETTON_MASTER_ADDRESS", "") or "")
                or None
            ),
            "jetton_decimals": 6,
            "forward_payload_text": str(payload),
            "fee_message_ton_amount": (
                str(getattr(S, "JETTON_TRANSFER_FEE_NANO", "") or "")
                or None
            ),
            "forward_ton_amount": (
                str(
                    getattr(
                        S,
                        "JETTON_FORWARD_TON_AMOUNT_NANO",
                        "1",
                    )
                    or "1"
                )
            ),
            "recipient_strategy": "owner_derived_wallet",
            "usdt_checkout_mode": get_usdt_checkout_mode(),
        }

    return {
        "tonconnect_transport_kind": None,
        "jetton_master_address": None,
        "jetton_decimals": None,
        "forward_payload_text": str(payload),
        "fee_message_ton_amount": None,
        "forward_ton_amount": None,
        "recipient_strategy": None,
        "usdt_checkout_mode": get_usdt_checkout_mode(),
    }


def build_tonconnect_tx(
    *,
    to_address: str,
    payload: str,
    asset: str,
    external_amount_atomic: int | str | None = None,
    amount_asset_d8: Decimal | None = None,
    valid_until: int | None = None,
) -> dict[str, Any] | None:
    """Собрать TonConnect transaction из server-owned atomic intent truth."""
    asset_u = str(asset or "TON").upper()
    if valid_until is None:
        ttl_sec = _ttl_minutes() * 60
        valid_until = int(utcnow().timestamp()) + int(ttl_sec)
    if external_amount_atomic is None:
        if amount_asset_d8 is None:
            raise ValueError("EXTERNAL_AMOUNT_ATOMIC_REQUIRED")
        external = external_amount_from_display(
            asset_u, amount_asset_d8, require_positive=True
        )
    else:
        external = external_amount_from_atomic(
            asset_u, external_amount_atomic, require_positive=True
        )
    if asset_u == "TON":
        return {
            "validUntil": int(valid_until),
            "messages": [{
                "address": str(to_address or "").strip(),
                "amount": str(external.atomic),
                "payload": str(payload),
            }],
        }
    if asset_u == "USDT":
        return None
    raise ValueError("ASSET_NOT_SUPPORTED")


def _payments_receiver_address() -> str:
    value = str(
        S.PAYMENTS_RECEIVER_ADDRESS
        or S.TON_MAIN_WALLET
        or ""
    ).strip()
    if not value:
        raise ValueError("TO_ADDRESS_NOT_SET")
    return value


async def _find_intent_by_idempotency(
    db: AsyncSession,
    *,
    owner_global_id_db: int,
    purpose: str,
    idempotency_key: str,
) -> dict[str, Any] | None:
    row = (
        await db.execute(
            text(
                """
                SELECT * FROM efhc_core.payment_intents
                 WHERE global_id = :global_id
                   AND purpose = :purpose
                   AND idempotency_key = :idempotency_key
                 LIMIT 1
                """
            ),
            {
                "global_id": int(owner_global_id_db),
                "purpose": str(purpose),
                "idempotency_key": str(idempotency_key),
            },
        )
    ).mappings().first()
    return dict(row) if row is not None else None


def _assert_intent_fingerprint(
    row: Mapping[str, Any],
    *,
    package_id: int | None,
    asset: str,
    amount_asset_d8: Decimal | None,
    efhc_amount_d8: Decimal,
    to_address: str,
    external_amount_atomic: int | str | None = None,
) -> None:
    """Проверить immutable fingerprint; v2 authority = asset-native atomic amount."""
    saved_package_id = row.get("package_id")
    package_matches = (
        saved_package_id is None and package_id is None
    ) or (
        saved_package_id is not None and package_id is not None
        and int(saved_package_id) == int(package_id)
    )
    asset_u = str(asset or "").upper()
    parsed = parse_intent_payload(str(row.get("payload") or ""))
    if parsed and int(parsed.get("payload_version") or 1) >= 2:
        if external_amount_atomic is None:
            amount_matches = False
        else:
            try:
                incoming = external_amount_from_atomic(
                    asset_u, external_amount_atomic, require_positive=True
                )
                amount_matches = (
                    str(parsed.get("asset") or "").upper() == asset_u
                    and int(parsed.get("external_amount_atomic") or -1) == incoming.atomic
                    and int(parsed.get("external_decimals") or -1) == incoming.decimals
                )
            except ValueError:
                amount_matches = False
    else:
        try:
            if amount_asset_d8 is None:
                amount_matches = False
            else:
                saved_external = external_amount_from_display(
                    asset_u, row.get("amount_asset_d8") or 0
                )
                incoming_external = external_amount_from_display(
                    asset_u, amount_asset_d8
                )
                amount_matches = saved_external.atomic == incoming_external.atomic
        except ValueError:
            amount_matches = False
    fingerprint_ok = (
        package_matches
        and str(row.get("asset") or "").upper() == asset_u
        and amount_matches
        and d8(row.get("efhc_amount_d8")) == d8(efhc_amount_d8)
        and str(row.get("to_address") or "").strip() == str(to_address or "").strip()
    )
    if not fingerprint_ok:
        raise IdempotencyPayloadConflictError(
            "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD"
        )


def _intent_valid_until(row: Mapping[str, Any]) -> int:
    expires_at = row.get("expires_at")
    timestamp = getattr(expires_at, "timestamp", None)
    if callable(timestamp):
        return int(timestamp())
    raise ValueError("INTENT_EXPIRES_AT_INVALID")


async def _create_intent_row_in_transaction(
    db: AsyncSession,
    *,
    owner: FinancialWriteOwner,
    purpose: str,
    package_id: int | None,
    asset: str,
    amount_asset_d8: Decimal | None,
    efhc_amount_d8: Decimal,
    idempotency_key: str,
    to_address: str,
    external_amount_atomic: int | str | None = None,
) -> dict[str, Any]:
    owner_global_id = str(global_id_from_database(owner.global_id))
    owner_global_id_db = global_id_from_database(owner.global_id).to_database()
    asset_u = str(asset or "").upper()
    if external_amount_atomic is None:
        if amount_asset_d8 is None:
            raise ValueError("EXTERNAL_AMOUNT_ATOMIC_REQUIRED")
        external = external_amount_from_display(
            asset_u, amount_asset_d8, require_positive=True
        )
    else:
        external = external_amount_from_atomic(
            asset_u, external_amount_atomic, require_positive=True
        )
    existing = await _find_intent_by_idempotency(
        db, owner_global_id_db=owner_global_id_db, purpose=purpose,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        _assert_intent_fingerprint(
            existing, package_id=package_id, asset=asset_u,
            amount_asset_d8=amount_asset_d8, efhc_amount_d8=efhc_amount_d8,
            to_address=to_address, external_amount_atomic=external.atomic,
        )
        return existing
    if purpose == "shop_external":
        await require_no_active_shop_preparation(db, global_id=owner_global_id_db)
    await _assert_pending_intent_limit(db, global_id=owner_global_id, purpose=purpose)
    now = utcnow()
    expires_at = now + timedelta(minutes=_ttl_minutes())
    next_id = int((await db.execute(
        text("SELECT nextval(" + _PI_SEQUENCE_EXPR + ")"),
        {"pi_table": PI_SEQUENCE_OWNER},
    )).scalar_one())
    payload = build_payload(
        purpose=purpose, intent_id=next_id, global_id=owner_global_id,
        asset=asset_u, external_amount_atomic=external.atomic,
    )
    compatibility_amount = _legacy_external_amount_d8(external.display)
    row = (await db.execute(
        text(
            """
            INSERT INTO efhc_core.payment_intents (
                id, tg_id, global_id, purpose, package_id, asset,
                amount_asset_d8, efhc_amount_d8, status,
                idempotency_key, payload, to_address, external_tx_hash,
                created_at, expires_at, updated_at
            )
            VALUES (
                :id, :tg_id, :global_id, :purpose, :package_id,
                :asset, :amount_asset_d8, :efhc_amount_d8, :status,
                :idempotency_key, :payload, :to_address, NULL,
                :now, :expires_at, :now
            )
            ON CONFLICT (global_id, purpose, idempotency_key)
            DO NOTHING
            RETURNING *
            """
        ),
        {
            "id": next_id, "tg_id": owner.provider_tg_id,
            "global_id": owner_global_id_db, "purpose": purpose,
            "package_id": package_id, "asset": asset_u,
            "amount_asset_d8": compatibility_amount,
            "efhc_amount_d8": d8(efhc_amount_d8), "status": STATUS_PENDING,
            "idempotency_key": idempotency_key, "payload": payload,
            "to_address": to_address, "now": now, "expires_at": expires_at,
        },
    )).mappings().first()
    if row is None:
        concurrent = await _find_intent_by_idempotency(
            db, owner_global_id_db=owner_global_id_db, purpose=purpose,
            idempotency_key=idempotency_key,
        )
        if concurrent is None:
            raise ValueError("INTENT_CREATE_FAILED")
        _assert_intent_fingerprint(
            concurrent, package_id=package_id, asset=asset_u,
            amount_asset_d8=amount_asset_d8, efhc_amount_d8=efhc_amount_d8,
            to_address=to_address, external_amount_atomic=external.atomic,
        )
        return concurrent
    return dict(row)


async def _create_intent_row(
    db: AsyncSession,
    **kwargs: Any,
) -> dict[str, Any]:
    """Compatibility root wrapper для standalone intent creators."""
    try:
        result = await _create_intent_row_in_transaction(db, **kwargs)
        await db.commit()
        return result
    except BaseException:
        await db.rollback()
        raise


def _external_truth_from_row(row: Mapping[str, Any]):
    asset = str(row.get("asset") or "").upper()
    parsed = parse_intent_payload(str(row.get("payload") or ""))
    if parsed and int(parsed.get("payload_version") or 1) >= 2:
        return external_amount_from_atomic(
            asset, int(parsed["external_amount_atomic"]), require_positive=True
        )
    return external_amount_from_display(
        asset, row.get("amount_asset_d8") or 0, require_positive=True
    )


def _intent_response(*, row: Mapping[str, Any]) -> dict[str, Any]:
    """Построить ответ из DB row; v2 external authority берётся из payload."""
    payload = str(row["payload"])
    asset = str(row["asset"]).upper()
    external = _external_truth_from_row(row)
    efhc_amount_d8 = d8(row["efhc_amount_d8"])
    to_address = str(row["to_address"])
    tx = build_tonconnect_tx(
        to_address=to_address, payload=payload, asset=asset,
        external_amount_atomic=external.atomic,
        valid_until=_intent_valid_until(row),
    )
    result: dict[str, Any] = {
        "intent_id": int(row["id"]),
        "global_id": str(global_id_from_database(int(row["global_id"]))),
        "purpose": str(row["purpose"]),
        "asset": asset,
        "external_amount_atomic": str(external.atomic),
        "external_decimals": external.decimals,
        "external_amount_display": external.display_text,
        "amount_asset_d8": str(row["amount_asset_d8"]),
        "efhc_amount_d8": str(efhc_amount_d8),
        "to_address": to_address,
        "tonconnect_tx": tx,
        "payload": payload,
        "expires_at": row["expires_at"],
    }
    result.update(build_transport_meta(asset=asset, payload=payload))
    return result


async def create_intent_deposit_by_package(
    db: AsyncSession,
    *,
    global_id: str,
    idempotency_key: str,
    package_id: int,
) -> dict[str, Any]:
    """Create an idempotent package intent for canonical owner."""
    if not idempotency_key:
        raise ValueError("IDEMPOTENCY_REQUIRED")
    owner = await resolve_and_lock_financial_write_owner(
        db, global_id=_global_id_db(global_id)
    )
    from app.models.shop_models import ShopItem  # noqa: WPS433
    from sqlalchemy import select  # noqa: PLC0415

    obj = (
        await db.execute(
            select(ShopItem)
            .where(ShopItem.id == int(package_id))
            .where(ShopItem.is_active.is_(True))
            .where(ShopItem.quantity_efhc.is_not(None))
            .limit(1)
        )
    ).scalars().first()
    if not obj:
        raise ValueError("PACKAGE_NOT_FOUND")
    extra = obj.extra or {}
    if extra.get("price_asset_d8") is None:
        raise ValueError("PACKAGE_PRICE_NOT_SET")
    asset = str(extra.get("asset") or "TON").upper()
    if asset not in {"TON", "USDT"}:
        raise ValueError("ASSET_NOT_SUPPORTED")
    to_address = _payments_receiver_address()
    amount_asset = external_amount_from_display(
        asset, extra.get("price_asset_d8"), require_positive=True
    )
    efhc_amount = d8(obj.quantity_efhc)
    row = await _create_intent_row(
        db,
        owner=owner,
        purpose="deposit_efhc",
        package_id=int(package_id),
        asset=asset,
        amount_asset_d8=amount_asset.display,
        external_amount_atomic=amount_asset.atomic,
        efhc_amount_d8=efhc_amount,
        idempotency_key=str(idempotency_key),
        to_address=to_address,
    )
    return _intent_response(row=row)



async def create_intent_deposit_custom(
    db: AsyncSession,
    *,
    global_id: str,
    idempotency_key: str,
    asset: str,
    amount_asset_d8: Decimal,
    efhc_amount_d8: Decimal,
) -> dict[str, Any]:
    """Create custom deposit intent for canonical owner."""
    if not idempotency_key:
        raise ValueError("IDEMPOTENCY_REQUIRED")
    owner = await resolve_and_lock_financial_write_owner(
        db, global_id=_global_id_db(global_id)
    )
    asset_u = str(asset or "TON").upper()
    if asset_u not in {"TON", "USDT"}:
        raise ValueError("ASSET_NOT_SUPPORTED")
    amount_asset = external_amount_from_display(
        asset_u, amount_asset_d8, require_positive=True
    )
    efhc_amount = d8(efhc_amount_d8)
    to_address = _payments_receiver_address()
    row = await _create_intent_row(
        db, owner=owner, purpose="deposit_efhc", package_id=None,
        asset=asset_u, amount_asset_d8=amount_asset.display,
        external_amount_atomic=amount_asset.atomic, efhc_amount_d8=efhc_amount,
        idempotency_key=str(idempotency_key),
        to_address=to_address,
    )
    return _intent_response(row=row)



async def create_intent_shop_external_in_transaction(
    db: AsyncSession,
    *,
    global_id: str,
    idempotency_key: str,
    asset: str,
    to_address: str,
    external_amount_atomic: int | str | None = None,
    amount_asset_d8: Decimal | None = None,
    efhc_amount_d8: Decimal | str | None = None,
) -> dict[str, Any]:
    """Создать shop PaymentIntent без root commit/rollback; v2 authority = atomic."""
    if not idempotency_key:
        raise ValueError("IDEMPOTENCY_REQUIRED")
    owner = await resolve_and_lock_financial_write_owner(
        db, global_id=_global_id_db(global_id)
    )
    asset_u = str(asset or "TON").upper()
    if asset_u not in {"TON", "USDT"}:
        raise ValueError("ASSET_NOT_SUPPORTED")
    if external_amount_atomic is None:
        if amount_asset_d8 is None:
            raise ValueError("EXTERNAL_AMOUNT_ATOMIC_REQUIRED")
        external = external_amount_from_display(
            asset_u, amount_asset_d8, require_positive=True
        )
    else:
        external = external_amount_from_atomic(
            asset_u, external_amount_atomic, require_positive=True
        )
    target = str(to_address or "").strip()
    if not target:
        raise ValueError("TO_ADDRESS_NOT_SET")
    shop_efhc_amount = d8(efhc_amount_d8 or "0")
    if shop_efhc_amount < d8("0"):
        raise ValueError("EFHC_AMOUNT_INVALID")
    row = await _create_intent_row_in_transaction(
        db, owner=owner, purpose="shop_external", package_id=None,
        asset=asset_u, amount_asset_d8=external.display,
        external_amount_atomic=external.atomic, efhc_amount_d8=shop_efhc_amount,
        idempotency_key=str(idempotency_key), to_address=target,
    )
    return _intent_response(row=row)


async def create_intent_shop_external(
    db: AsyncSession,
    *,
    global_id: str,
    idempotency_key: str,
    asset: str,
    to_address: str,
    external_amount_atomic: int | str | None = None,
    amount_asset_d8: Decimal | None = None,
    efhc_amount_d8: Decimal | str | None = None,
) -> dict[str, Any]:
    """Compatibility root wrapper для standalone shop-intent callers."""
    try:
        result = await create_intent_shop_external_in_transaction(
            db, global_id=global_id, idempotency_key=idempotency_key,
            asset=asset, to_address=to_address,
            external_amount_atomic=external_amount_atomic,
            amount_asset_d8=amount_asset_d8,
            efhc_amount_d8=efhc_amount_d8,
        )
        await db.commit()
        return result
    except BaseException:
        await db.rollback()
        raise


async def list_recent_intents_for_user(
    db: AsyncSession,
    *,
    global_id: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return recent payment intents for canonical owner."""
    limit = max(1, min(int(limit), 50))
    q = text(
        "\n".join(
            [
                "SELECT id",
                "  FROM efhc_core.payment_intents",
                " WHERE global_id = :global_id",
                " ORDER BY id DESC",
                " LIMIT :lim",
            ]
        )
    )
    rows = (
        (
            await db.execute(
                q,
                {"global_id": _global_id_db(global_id), "lim": limit},
            )
        )
        .mappings()
        .all()
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        item = await get_intent_status_for_user(
            db,
            global_id=global_id,
            intent_id=int(row["id"]),
        )
        if item.get("ok"):
            out.append(item)
    return out


async def get_intent_status_for_user(
    db: AsyncSession,
    *,
    global_id: str,
    intent_id: int,
) -> dict[str, Any]:
    """Вернуть состояние платёжного намерения canonical owner."""
    q = text(
        "\n".join(
            [
                "SELECT id, global_id, purpose, asset,",
                "       amount_asset_d8::numeric,",
                "       efhc_amount_d8::numeric,",
                "       status, payload, to_address,",
                "       external_tx_hash,",
                "       created_at, expires_at",
                "  FROM efhc_core.payment_intents",
                " WHERE id = :iid AND global_id = :global_id",
                " LIMIT 1",
            ]
        )
    )
    row = (
        await db.execute(
            q,
            {"iid": int(intent_id), "global_id": _global_id_db(global_id)},
        )
    ).mappings().first()
    if not row:
        return {"ok": False}

    order = None
    if str(row.get("purpose") or "") == "shop_external":
        order_q = text(
            "\n".join(
                [
                    "SELECT id, status, payment_error_log",
                    "  FROM efhc_core.shop_orders",
                    " WHERE global_id = :global_id",
                    "   AND (extra ->> 'intent_id') = :iid",
                    " ORDER BY id DESC",
                    " LIMIT 1",
                ]
            )
        )
        order = (
            await db.execute(
                order_q,
                {
                    "global_id": _global_id_db(global_id),
                    "iid": str(intent_id),
                },
            )
        ).mappings().first()

    inbox_q = text(
        "\n".join(
            [
                "SELECT tx_hash, status, last_error",
                "  FROM efhc_core.ton_inbox_logs",
                " WHERE memo = :memo",
                "    OR tx_hash = :tx_hash",
                " ORDER BY created_at DESC, id DESC",
                " LIMIT 1",
            ]
        )
    )
    inbox_row = (
        await db.execute(
            inbox_q,
            {
                "memo": str(row.get("payload") or ""),
                "tx_hash": str(row.get("external_tx_hash") or ""),
            },
        )
    ).mappings().first()
    inbox = dict(inbox_row) if inbox_row else None
    order_map = dict(order) if order is not None else None
    flow_truth = _build_intent_flow_truth(
        purpose=str(row.get("purpose") or ""),
        intent_status=str(row.get("status") or ""),
        expires_at=row.get("expires_at"),
        external_tx_hash=(
            str(row.get("external_tx_hash") or "") or None
        ),
        order=order_map,
        inbox=inbox,
    )
    row_map = dict(row)
    external_truth = _external_truth_from_row(row_map)
    out = {
        "ok": True,
        "id": int(row["id"]),
        "global_id": str(global_id_from_database(row["global_id"])),
        "purpose": str(row["purpose"]),
        "asset": str(row["asset"]),
        "amount_asset_d8": str(row["amount_asset_d8"]),
        "external_amount_atomic": str(external_truth.atomic),
        "external_decimals": external_truth.decimals,
        "external_amount_display": external_truth.display_text,
        "efhc_amount_d8": (
            str(row["efhc_amount_d8"])
            if row["efhc_amount_d8"] is not None
            else None
        ),
        "status": str(row["status"]),
        "payload": str(row["payload"]),
        "to_address": str(row["to_address"]),
        "external_tx_hash": row["external_tx_hash"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "flow_truth": flow_truth,
    }
    if order_map is not None:
        out["order"] = order_map
    if inbox is not None:
        out["inbox"] = inbox
    return out
