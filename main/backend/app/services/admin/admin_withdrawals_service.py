# backend/app/services/admin/admin_withdrawals_service.py
# ======================================================================
# EFHC Bot — Сервис выдачи EFHC и NFT (выводы, бонусы)
# ----------------------------------------------------------------------
# Назначение модуля:
# • Управление заявками на вывод EFHC пользователями.
# • Legacy-контур бонусных выплат EFHC (bonus_awards) guarded/no-op.
#
# Жёсткие каноны:
# 1) НЕТ внутренних переводов между пользователями (P2P).
# Любое движение EFHC:
# Банк ↔ Пользователь
# и только через банковский сервис (transactions_service).
# 2) Все бонусные начисления идут только в бонусный баланс пользователя
# (bonus_balance / bonus ветка банка).
# 3) Все операции (выводы, бонусы) ИДЕМПОТЕНТНЫ:
# - обязательный idempotency_key (админ/система передаёт его явно),
# - повторные вызовы с тем же ключом не создают дублей.
# 4) Для бонусов есть возможность фильтрации по VIP-статусу
# пользователя (is_vip) для приоритизации обработки.
# 5) Изменение статусов в таблицах:
# • withdrawal_requests: PENDING → PAID/REJECTED/CANCELED
# • bonus_awards:       LEGACY_BONUS_AWARDS_NO_ACTIVE_TABLE.
#
# Где храним данные:
# • efhc_core.withdraw_requests — заявки на вывод EFHC.
# • efhc_admin.bonus_awards — legacy/dead-code таблица, неактивна.
#
# ВНИМАНИЕ:
# • Финансовые изменения балансов всегда делегируются в
# app.services.transactions_service
# и нигде в этом модуле балансы пользователей напрямую не обновляются.
# ======================================================================

from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal
from typing import Any, Literal

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.core.sql_aliases_core import canon_schema
from app.core.utils_core import (
    format_decimal_str,
)
from app.identity.api_contract import ApiExternalGlobalId
from app.integrations.ton_api import TonAPIClient, TonAPIEvent
from app.schemas.id_schemas import ApiLifetimeId
from app.services.common_errors import EfhcConflictError
from app.services.outcome_service import (
    build_withdraw_outcome_bundle,
    save_withdraw_outcome_event,
    send_withdraw_outcome_telegram_notification,
)
from app.services.wallets_service import InvalidWalletAddress, normalize_wallet_address
from app.services.transactions_service import (
    credit_user_bonus_from_bank,
    credit_user_from_bank_nocommit,
    debit_user_to_bank_nocommit,
)
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.engine import Result
from sqlalchemy.ext.asyncio import AsyncSession

from .admin_logging import AdminLogger
from .admin_notifications import AdminNotifier
from .admin_rbac import RBAC, AdminRole, AdminUser
from .admincommoncrud import AdminCommonCrud

logger = get_logger(__name__)
S = get_settings()

SCHEMA_ADMIN: str = canon_schema(
    getattr(S, "DB_SCHEMA_ADMIN", "efhc_admin") or "efhc_admin",
)
SCHEMA_CORE: str = canon_schema(
    getattr(S, "DB_SCHEMA_CORE", "efhc_core") or "efhc_core",
)


async def _deliver_withdraw_notifications_after_commit(
    db: AsyncSession,
    *,
    bundle: Any,
    notification_id: int,
    event: str,
    message: str,
) -> None:
    """Доставить сетевые withdrawal-уведомления только после commit."""
    try:
        delivered = await send_withdraw_outcome_telegram_notification(
            db,
            bundle=bundle,
        )
        await db.commit()
        bundle.metadata["telegram_delivery"] = (
            "sent" if delivered else "failed"
        )
    except Exception as exc:
        await db.rollback()
        bundle.metadata["telegram_delivery"] = "unknown"
        logger.warning(
            "post-commit withdrawal outcome delivery failed: %s",
            exc,
        )
    try:
        await AdminNotifier.send_telegram_after_commit(
            notification_id=int(notification_id),
            event=event,
            message=message,
        )
    except Exception as exc:
        logger.warning(
            "post-commit Admin withdrawal notification failed: %s",
            exc,
        )

EFHC_DECIMALS: int = int(getattr(S, "EFHC_DECIMALS", 8) or 8)


def _normalize_withdraw_tx_hash(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("WITHDRAWAL_TX_HASH_REQUIRED")
    if not (16 <= len(raw) <= 128):
        raise ValueError("WITHDRAWAL_TX_HASH_INVALID")
    if any(ch.isspace() or ord(ch) < 33 or ord(ch) > 126 for ch in raw):
        raise ValueError("WITHDRAWAL_TX_HASH_INVALID")
    return raw


def _withdraw_event_matches_amount(event: TonAPIEvent, amount_efhc: Decimal) -> bool:
    expected_atomic = d8(amount_efhc) * (Decimal(10) ** EFHC_DECIMALS)
    return event.amount_asset == expected_atomic


async def _verify_withdrawal_tx_onchain(
    *,
    tx_hash: str,
    recipient_address: str,
    amount_efhc: Decimal,
) -> TonAPIEvent:
    """Verify one EFHC Jetton payout against recipient-side TON history.

    This is deliberately fail-closed: absence, wrong asset/master or wrong
    amount never upgrades a withdrawal to PAID.
    """
    tx = _normalize_withdraw_tx_hash(tx_hash)
    recipient = str(recipient_address or "").strip()
    if not recipient:
        raise EfhcConflictError("WITHDRAWAL_RECIPIENT_ADDRESS_REQUIRED")

    events = await TonAPIClient().get_incoming_payments(
        recipient,
        limit=200,
    )
    exact = [event for event in events if str(event.tx_hash).strip() == tx]
    if not exact:
        raise EfhcConflictError("WITHDRAWAL_TX_NOT_CONFIRMED_ONCHAIN")

    expected_master = str(
        getattr(S, "EFHC_JETTON_MASTER_ADDRESS", "") or ""
    ).strip().upper()
    for event in exact:
        if str(event.asset or "").upper() != "JETTON":
            continue
        if str(event.jetton_master or "").strip().upper() != expected_master:
            continue
        if not _withdraw_event_matches_amount(event, amount_efhc):
            continue
        return event

    raise EfhcConflictError("WITHDRAWAL_TX_ONCHAIN_MISMATCH")


async def _claim_withdrawal_tx_hash(
    db: AsyncSession,
    *,
    withdrawal_id: int,
    tx_hash: str,
) -> None:
    """Serialize tx-hash ownership and reject reuse by another withdrawal."""
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:tx_hash))"),
        {"tx_hash": tx_hash},
    )
    other = (
        await db.execute(
            text(
                """
                SELECT id
                  FROM efhc_core.withdraw_requests
                 WHERE tx_hash = :tx_hash
                   AND id <> :wid
                 LIMIT 1
                """
            ),
            {"tx_hash": tx_hash, "wid": int(withdrawal_id)},
        )
    ).scalar_one_or_none()
    if other is not None:
        raise EfhcConflictError("WITHDRAWAL_TX_HASH_ALREADY_USED")
_Q = Decimal(1).scaleb(-EFHC_DECIMALS)

LEGACY_BONUS_AWARDS_NO_ACTIVE_TABLE = (
    "LEGACY_BONUS_AWARDS_NO_ACTIVE_TABLE"
)


def d8(x: Any) -> Decimal:
    """Округление вниз до EFHC_DECIMALS знаков (канон для EFHC)."""
    return Decimal(str(x)).quantize(_Q, rounding=ROUND_DOWN)


async def _legacy_bonus_awards_table_exists(db: AsyncSession) -> bool:
    """Return True only if the deprecated bonus_awards table exists.

    DB drift closure canon: bonus_awards is not an active table.
    Historical references require this explicit legacy guard.
    """
    sql = text(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = :schema
          AND table_name = 'bonus_awards'
        LIMIT 1
        """
    )
    r: Result = await db.execute(sql, {"schema": SCHEMA_ADMIN})
    return r.fetchone() is not None


async def _ensure_legacy_bonus_awards_table(db: AsyncSession) -> None:
    """Fail closed when legacy bonus_awards table is not present."""
    if await _legacy_bonus_awards_table_exists(db):
        return
    raise ValueError(
        LEGACY_BONUS_AWARDS_NO_ACTIVE_TABLE
        + ": bonus_awards is documented legacy/dead code"
    )


# ======================================================================
# Общие DTO и перечисления
# ======================================================================

_WithdrawSt = Literal[
    "PENDING",
    "PAID",
    "REJECTED",
    "CANCELED",
]


class WithdrawalStatus(str):
    """Статусы заявок на вывод EFHC."""

    PENDING = "PENDING"  # создана, ждёт обработки
    PAID = "PAID"  # успешно выплачена
    REJECTED = "REJECTED"  # отклонена админом
    CANCELED = "CANCELED"  # отменена


class BonusAwardStatus(str):
    """Статусы бонусных выплат EFHC (bonus_awards)."""

    PENDING = "PENDING"
    PAID = "PAID"
    REJECTED = "REJECTED"
    ERROR = "ERROR"


class WithdrawalFilters(BaseModel):
    """Фильтры заявок по canonical account owner."""

    global_id: ApiExternalGlobalId | None = None
    status: _WithdrawSt | None = None
    vip_only: bool = False
    limit: int = Field(100, ge=1, le=500)
    offset: int = Field(0, ge=0)
    sort_desc: bool = True


class BonusAwardFilters(BaseModel):
    """Фильтры исторических бонусов по resolved global_id."""

    global_id: ApiExternalGlobalId | None = None
    status: _WithdrawSt | None = None
    source: str | None = None
    vip_only: bool = False
    limit: int = Field(100, ge=1, le=500)
    offset: int = Field(0, ge=0)
    sort_desc: bool = True


class WithdrawalRecord(BaseModel):
    """Строка списка заявок по canonical owner."""

    id: ApiLifetimeId
    global_id: ApiExternalGlobalId
    amount_efhc: str
    status: str
    external_address: str | None
    tx_hash: str | None
    created_at: str
    processed_at: str | None
    error_message: str | None
    is_vip: bool
    payout_asset: str = "EFHC"
    tonconnect_transport_kind: str | None = "jetton_transfer"
    jetton_master_address: str | None = None
    jetton_decimals: int | None = None
    fee_message_ton_amount: str | None = None


class BonusAwardRecord(BaseModel):
    """Историческая bonus_awards строка с resolved owner."""

    id: int
    global_id: ApiExternalGlobalId
    amount_efhc: str
    status: str
    source: str
    created_at: str
    processed_at: str | None
    meta_json: str | None
    is_vip: bool


class WithdrawalPayoutReserveRequest(BaseModel):
    """Pre-execution reservation request for an Admin wallet payout.

    ``sender_wallet_address`` is only a claimed transport address. The
    authoritative sender is resolved server-side from the current Admin
    account primary, active, proof-verified wallet binding.
    """

    sender_wallet_address: str | None = Field(default=None, max_length=255)
    wallet_provider: str | None = Field(default=None, max_length=64)


class WithdrawalApproveRequest(BaseModel):
    """
    Запрос на подтверждение/выплату заявки на вывод.

    tx_hash                — внешний tx, можно указать позже.
    payout_ref             — proof/ref строки wallet-send события.
    wallet_send_confirmed  — был ли подтверждён факт нажатия Send.
    wallet_provider        — Tonkeeper / MyTonWallet / другой runtime.
    sender_wallet_address  — адрес кошелька оператора.
    idempotency_key        — ключ идемпотентности дебета.
    """

    tx_hash: str | None = None
    payout_ref: str | None = Field(default=None, max_length=255)
    wallet_send_confirmed: bool = False
    wallet_provider: str | None = Field(default=None, max_length=64)
    sender_wallet_address: str | None = Field(
        default=None,
        max_length=255,
    )
    confirmation_mode: Literal["wallet_send", "manual"] | None = None
    reason: str | None = Field(default=None, max_length=500)
    comment_override: str | None = Field(default=None, max_length=1500)
    comment_auto_translated: bool = False
    idempotency_key: str = Field(..., min_length=1, max_length=128)

    @field_validator("idempotency_key")
    def _v_idem(cls, v: str) -> str:
        """Валидация idempotency_key."""
        v = (v or "").strip()
        if not v:
            raise ValueError("idempotency_key обязателен")
        return v


class BonusAwardProcessRequest(BaseModel):
    """
    Запрос на выплату бонуса EFHC из bonus_awards.

    Для совместимости с outcome-service допускаем такой же
    payload подтверждения, как и у обычного approve path.
    """

    tx_hash: str | None = None
    payout_ref: str | None = Field(default=None, max_length=255)
    wallet_send_confirmed: bool = False
    wallet_provider: str | None = Field(default=None, max_length=64)
    sender_wallet_address: str | None = Field(
        default=None,
        max_length=255,
    )
    comment_override: str | None = Field(default=None, max_length=1500)
    comment_auto_translated: bool = False
    idempotency_key: str = Field(..., min_length=1, max_length=128)

    @field_validator("idempotency_key")
    def _v_idem(cls, v: str) -> str:
        """Валидация idempotency_key."""
        v = (v or "").strip()
        if not v:
            raise ValueError("idempotency_key обязателен")
        return v


# ======================================================================
# Admin payout pre-execution reservation
# ======================================================================

_PAYOUT_RESERVATION_PREFIX = "wpr1"


def _build_payout_reservation_ref(
    *,
    admin_global_id: int,
    wallet_binding_id: int,
    withdrawal_id: int,
) -> str:
    token = secrets.token_hex(8)
    return (
        f"{_PAYOUT_RESERVATION_PREFIX}:{int(admin_global_id)}:"
        f"{int(wallet_binding_id)}:{int(withdrawal_id)}:{token}"
    )


def _parse_payout_reservation_ref(value: str | None) -> tuple[int, int, int] | None:
    raw = str(value or "").strip()
    parts = raw.split(":")
    if len(parts) != 5 or parts[0] != _PAYOUT_RESERVATION_PREFIX:
        return None
    try:
        admin_global_id = int(parts[1])
        wallet_binding_id = int(parts[2])
        withdrawal_id = int(parts[3])
    except (TypeError, ValueError):
        return None
    if admin_global_id <= 0 or wallet_binding_id <= 0 or withdrawal_id <= 0:
        return None
    if not parts[4]:
        return None
    return admin_global_id, wallet_binding_id, withdrawal_id


async def _load_admin_wallet_binding(
    db: AsyncSession,
    *,
    admin: AdminUser,
    wallet_binding_id: int | None = None,
    require_primary: bool = True,
    require_active_verified: bool = True,
) -> Any:
    conditions = ["global_id = :global_id"]
    if require_active_verified:
        conditions.extend(["is_active = TRUE", "proof_verified = TRUE"])
    params: dict[str, Any] = {"global_id": int(admin.global_id)}
    if wallet_binding_id is not None:
        conditions.append("id = :wallet_id")
        params["wallet_id"] = int(wallet_binding_id)
    if require_primary:
        conditions.append("is_primary = TRUE")
    rows = (
        await db.execute(
            text(
                "SELECT id, wallet_address, wallet_app, is_primary, "
                "is_active, proof_verified "
                f"FROM {SCHEMA_CORE}.wallet_bindings "
                f"WHERE {' AND '.join(conditions)} "
                "ORDER BY id ASC LIMIT 2"
            ),
            params,
        )
    ).fetchall()
    if len(rows) != 1:
        raise EfhcConflictError("ADMIN_PRIMARY_WALLET_AUTHORITY_REQUIRED")
    return rows[0]


def _assert_claimed_sender_matches_binding(
    claimed: str | None,
    *,
    binding_address: str,
) -> None:
    if not claimed:
        return
    try:
        canonical = normalize_wallet_address(str(claimed))
    except InvalidWalletAddress as exc:
        raise EfhcConflictError("ADMIN_PAYOUT_SENDER_WALLET_MISMATCH") from exc
    if canonical != str(binding_address):
        raise EfhcConflictError("ADMIN_PAYOUT_SENDER_WALLET_MISMATCH")


# ======================================================================
# Сервис обработки выводов и бонусов
# ======================================================================


class WithdrawalsService:
    """Admin-сервис очередей: выводы и бонусы."""

    # --------------------------------------------------------------
    # БЛОК 1. Список заявок на вывод EFHC
    # --------------------------------------------------------------

    @staticmethod
    async def list_withdrawals(
        db: AsyncSession,
        filters: WithdrawalFilters,
    ) -> list[WithdrawalRecord]:
        """Вернуть заявки, принадлежащие только ``global_id``."""
        where = ["1=1"]
        params: dict[str, Any] = {
            "limit": filters.limit,
            "offset": filters.offset,
        }
        if filters.global_id is not None:
            where.append("w.global_id = :global_id")
            params["global_id"] = int(filters.global_id)
        if filters.status is not None:
            where.append("w.status = :status")
            params["status"] = filters.status
        if filters.vip_only:
            where.append("u.is_vip = TRUE")
        order = "DESC" if filters.sort_desc else "ASC"
        items = await AdminCommonCrud.fetch_all(
            db,
            sql="\n".join(
                [
                    "SELECT w.id, w.global_id, w.amount, w.status,",
                    "       w.external_address, w.tx_hash,",
                    "       w.created_at, w.processed_at,",
                    "       w.error_message,",
                    "       COALESCE(u.is_vip, FALSE) AS is_vip",
                    "FROM " + SCHEMA_CORE + ".withdraw_requests w",
                    "JOIN " + SCHEMA_CORE + ".users u",
                    "  ON u.global_id = w.global_id",
                    f"WHERE {' AND '.join(where)}",
                    f"ORDER BY w.id {order}",
                    "LIMIT :limit OFFSET :offset",
                ]
            ),
            params=params,
        )
        out: list[WithdrawalRecord] = []
        for row in items:
            created = row.get("created_at")
            processed = row.get("processed_at")
            created_iso = getattr(created, "isoformat", None)
            processed_iso = getattr(processed, "isoformat", None)
            out.append(
                WithdrawalRecord(
                    id=int(row["id"]),
                    global_id=f"{int(row['global_id']):010d}",
                    amount_efhc=str(row["amount"]),
                    status=str(row["status"]),
                    external_address=row.get("external_address"),
                    tx_hash=row.get("tx_hash"),
                    created_at=(
                        created_iso()
                        if callable(created_iso)
                        else str(created)
                    ),
                    processed_at=(
                        processed_iso()
                        if callable(processed_iso)
                        else None
                    ),
                    error_message=row.get("error_message"),
                    is_vip=bool(row.get("is_vip")),
                    payout_asset="EFHC",
                    tonconnect_transport_kind="jetton_transfer",
                    jetton_master_address=(
                        str(
                            getattr(
                                S,
                                "EFHC_JETTON_MASTER_ADDRESS",
                                "",
                            )
                            or ""
                        )
                        or None
                    ),
                    jetton_decimals=int(
                        getattr(S, "EFHC_JETTON_DECIMALS", 8) or 8
                    ),
                    fee_message_ton_amount=(
                        str(
                            getattr(
                                S,
                                "JETTON_TRANSFER_FEE_NANO",
                                "",
                            )
                            or ""
                        )
                        or None
                    ),
                )
            )
        return out

    # --------------------------------------------------------------
    # БЛОК 2. Обработка заявки на вывод EFHC (approve / reject)
    # --------------------------------------------------------------

    @staticmethod
    async def reserve_payout_attempt(
        db: AsyncSession,
        *,
        withdrawal_id: int,
        req: WithdrawalPayoutReserveRequest,
        idempotency_key: str,
        admin: AdminUser,
    ) -> dict[str, Any]:
        """Create the exclusive server reservation before wallet Send.

        The reservation reuses the already-frozen UNIQUE
        ``processing_idempotency_key`` and ``payout_ref`` columns. A new
        reservation response is the only response with ``safe_to_send=True``.
        Recovered/replayed reservations are deliberately fail-closed because
        backend v1 has no on-chain proof that a previous wallet Send did not
        already happen.
        """
        RBAC.require_role(admin, AdminRole.MODERATOR)
        ik = str(idempotency_key or "").strip()
        if not ik:
            raise ValueError("idempotency_key обязателен")

        row = (
            await db.execute(
                text(
                    f"""
                    SELECT id, global_id, amount, status, external_address,
                           processing_idempotency_key, payout_ref
                      FROM {SCHEMA_CORE}.withdraw_requests
                     WHERE id = :wid
                     FOR UPDATE
                    """
                ),
                {"wid": int(withdrawal_id)},
            )
        ).fetchone()
        if not row:
            raise ValueError("Заявка на вывод не найдена")
        if str(row.status) != WithdrawalStatus.PENDING:
            raise EfhcConflictError("withdrawal is not pending")
        if not str(row.external_address or "").strip():
            raise EfhcConflictError("WITHDRAWAL_RECIPIENT_ADDRESS_REQUIRED")

        existing_ik = str(row.processing_idempotency_key or "").strip()
        existing_ref = str(row.payout_ref or "").strip()
        if existing_ik or existing_ref:
            parsed = _parse_payout_reservation_ref(existing_ref)
            if (
                existing_ik == ik
                and parsed is not None
                and parsed[0] == int(admin.global_id)
                and parsed[2] == int(withdrawal_id)
            ):
                binding = await _load_admin_wallet_binding(
                    db,
                    admin=admin,
                    wallet_binding_id=parsed[1],
                    require_primary=True,
                )
                _assert_claimed_sender_matches_binding(
                    req.sender_wallet_address,
                    binding_address=str(binding.wallet_address),
                )
                return {
                    "ok": True,
                    "status": WithdrawalStatus.PENDING,
                    "reserved": True,
                    "safe_to_send": False,
                    "recovered": True,
                    "request_id": int(withdrawal_id),
                    "idempotency_key": existing_ik,
                    "payout_ref": existing_ref,
                    "sender_wallet_address": str(binding.wallet_address),
                    "wallet_provider": binding.wallet_app,
                    "recipient_external_address": str(row.external_address),
                    "amount_efhc": format_decimal_str(d8(row.amount), EFHC_DECIMALS),
                }
            raise EfhcConflictError("WITHDRAWAL_PAYOUT_ALREADY_RESERVED")

        binding = await _load_admin_wallet_binding(
            db, admin=admin, require_primary=True
        )
        _assert_claimed_sender_matches_binding(
            req.sender_wallet_address,
            binding_address=str(binding.wallet_address),
        )
        payout_ref = _build_payout_reservation_ref(
            admin_global_id=int(admin.global_id),
            wallet_binding_id=int(binding.id),
            withdrawal_id=int(withdrawal_id),
        )
        updated = await db.execute(
            text(
                f"""
                UPDATE {SCHEMA_CORE}.withdraw_requests
                   SET processing_idempotency_key = :ik,
                       payout_ref = :payout_ref,
                       error_message = NULL,
                       updated_at = NOW() AT TIME ZONE 'UTC'
                 WHERE id = :wid
                   AND status = 'PENDING'
                   AND processing_idempotency_key IS NULL
                   AND payout_ref IS NULL
                """
            ),
            {"ik": ik, "payout_ref": payout_ref, "wid": int(withdrawal_id)},
        )
        if int(getattr(updated, "rowcount", 0) or 0) != 1:
            raise EfhcConflictError("WITHDRAWAL_PAYOUT_RESERVATION_RACE")
        await AdminLogger.write(
            db,
            actor_global_id=admin.global_id,
            admin_id=admin.id,
            action="WITHDRAWAL_PAYOUT_ATTEMPT_RESERVED",
            entity="withdrawal",
            entity_id=int(withdrawal_id),
            details=(
                f"payout_ref={payout_ref}; sender_wallet={binding.wallet_address}; "
                f"wallet_binding_id={binding.id}; recipient={row.external_address}; "
                f"amount={format_decimal_str(d8(row.amount), EFHC_DECIMALS)}"
            ),
            required=True,
        )
        await db.commit()
        return {
            "ok": True,
            "status": WithdrawalStatus.PENDING,
            "reserved": True,
            "safe_to_send": True,
            "recovered": False,
            "request_id": int(withdrawal_id),
            "idempotency_key": ik,
            "payout_ref": payout_ref,
            "sender_wallet_address": str(binding.wallet_address),
            "wallet_provider": binding.wallet_app,
            "recipient_external_address": str(row.external_address),
            "amount_efhc": format_decimal_str(d8(row.amount), EFHC_DECIMALS),
        }

    @staticmethod
    async def get_payout_reservation(
        db: AsyncSession,
        *,
        withdrawal_id: int,
        admin: AdminUser,
    ) -> dict[str, Any]:
        """Return an existing reservation for the same Admin only.

        Recovery never grants a new wallet Send authority. This is intentional
        until an on-chain reconciliation layer can disambiguate a crash around
        the external wallet transport.
        """
        RBAC.require_role(admin, AdminRole.MODERATOR)
        row = (
            await db.execute(
                text(
                    f"""
                    SELECT id, amount, status, external_address,
                           processing_idempotency_key, payout_ref
                      FROM {SCHEMA_CORE}.withdraw_requests
                     WHERE id = :wid
                    """
                ),
                {"wid": int(withdrawal_id)},
            )
        ).fetchone()
        if not row:
            raise ValueError("Заявка на вывод не найдена")
        ik = str(row.processing_idempotency_key or "").strip()
        payout_ref = str(row.payout_ref or "").strip()
        parsed = _parse_payout_reservation_ref(payout_ref)
        if not ik and not payout_ref:
            return {
                "ok": True,
                "status": str(row.status),
                "reserved": False,
                "safe_to_send": False,
                "recovered": False,
                "request_id": int(withdrawal_id),
            }
        if (
            parsed is None
            or parsed[0] != int(admin.global_id)
            or parsed[2] != int(withdrawal_id)
        ):
            raise EfhcConflictError("WITHDRAWAL_PAYOUT_RESERVED_BY_OTHER_CONTEXT")
        binding = await _load_admin_wallet_binding(
            db,
            admin=admin,
            wallet_binding_id=parsed[1],
            require_primary=False,
            require_active_verified=False,
        )
        return {
            "ok": True,
            "status": str(row.status),
            "reserved": True,
            "safe_to_send": False,
            "recovered": True,
            "request_id": int(withdrawal_id),
            "idempotency_key": ik,
            "payout_ref": payout_ref,
            "sender_wallet_address": str(binding.wallet_address),
            "wallet_provider": binding.wallet_app,
            "recipient_external_address": str(row.external_address or ""),
            "amount_efhc": format_decimal_str(d8(row.amount), EFHC_DECIMALS),
        }

    @staticmethod
    async def mark_withdrawal_paid(
        db: AsyncSession,
        *,
        withdrawal_id: int,
        req: WithdrawalApproveRequest,
        admin: AdminUser,
    ) -> dict[str, Any]:
        """
        Явно подтверждает факт внешней выплаты EFHC и ставит PAID.

          • wallet_send требует сохранённого/переданного payout evidence.
          • manual требует причины оператора.
          • Холдинг и required Admin audit сохраняются атомарно с PAID.
          • В случае ошибки:
              - статус заявки остаётся PENDING,
              - error_message заполняется,
              - исключение прокидывается наверх в «дружелюбном» виде.

        RBAC:
          • Минимум MODERATOR.
        """
        RBAC.require_role(admin, AdminRole.MODERATOR)
        if not req.idempotency_key.strip():
            raise ValueError("idempotency_key обязателен")

        # Берём заявку под лок (FOR UPDATE), чтобы не было гонки.
        r: Result = await db.execute(
            text(
                """
            SELECT
                    id,
                    tg_id,
                    global_id,
                    amount,
                    status,
                    idempotency_key,
                    hold_done,
                    refund_done,
                    external_address,
                    tx_hash,
                    payout_ref,
                    processing_idempotency_key,
                    error_message
                FROM efhc_core.withdraw_requests
                WHERE id = :wid
                FOR UPDATE"""
            ),
            {"wid": withdrawal_id},
        )
        row = r.fetchone()
        if not row:
            raise ValueError("Заявка на вывод не найдена")

        final_statuses = (
            WithdrawalStatus.PAID,
            WithdrawalStatus.REJECTED,
            WithdrawalStatus.CANCELED,
        )
        processing_ik = str(row.processing_idempotency_key or "")
        if row.status in final_statuses:
            if (
                row.status == WithdrawalStatus.PAID
                and processing_ik == req.idempotency_key
            ):
                return {
                    "ok": True,
                    "status": WithdrawalStatus.PAID,
                    "idempotency_key": req.idempotency_key,
                    "tx_hash": row.tx_hash,
                }
            logger.info(
                "approve_withdrawal: withdrawal_id=%s final=%s",
                withdrawal_id,
                row.status,
            )
            raise EfhcConflictError("already processed")

        # processing_idempotency_key may now be the pre-execution payout
        # reservation key. The same reserved key is allowed to continue into
        # finalization; any different key remains fail-closed.
        reserved_ref = _parse_payout_reservation_ref(row.payout_ref)
        reserved_same_context = bool(
            reserved_ref
            and reserved_ref[0] == int(admin.global_id)
            and reserved_ref[2] == int(withdrawal_id)
        )
        if processing_ik:
            if processing_ik != req.idempotency_key:
                raise EfhcConflictError(
                    "already processing with another key"
                )
            if not reserved_same_context:
                # Legacy same-key replay without a pre-execution reservation.
                logger.info(
                    "approve_withdrawal: legacy idem=%s wid=%s",
                    req.idempotency_key,
                    withdrawal_id,
                )
                return {
                    "ok": True,
                    "status": str(row.status),
                    "idempotency_key": req.idempotency_key,
                    "tx_hash": row.tx_hash,
                }

        mode = req.confirmation_mode
        if mode is None:
            mode = (
                "wallet_send"
                if (req.wallet_send_confirmed or req.payout_ref or req.tx_hash)
                else "manual"
            )
        manual_reason = str(req.reason or req.comment_override or "").strip()
        if mode == "manual" and not manual_reason:
            raise ValueError("WITHDRAWAL_MANUAL_PAID_REASON_REQUIRED")
        persisted_payout_ref = str(row.payout_ref or "").strip()
        persisted_tx_hash = str(row.tx_hash or "").strip()
        if mode == "wallet_send":
            if not req.wallet_send_confirmed:
                raise ValueError("WITHDRAWAL_WALLET_SEND_CONFIRMATION_REQUIRED")
            if not processing_ik or processing_ik != req.idempotency_key:
                raise EfhcConflictError("WITHDRAWAL_PAYOUT_RESERVATION_REQUIRED")
            if not reserved_same_context or reserved_ref is None:
                raise EfhcConflictError("WITHDRAWAL_PAYOUT_RESERVATION_REQUIRED")
            if str(req.payout_ref or "").strip() != persisted_payout_ref:
                raise EfhcConflictError("WITHDRAWAL_PAYOUT_REFERENCE_MISMATCH")
            if not persisted_tx_hash:
                raise EfhcConflictError("WITHDRAWAL_ONCHAIN_EVIDENCE_REQUIRED")
            if req.tx_hash and _normalize_withdraw_tx_hash(req.tx_hash) != persisted_tx_hash:
                raise EfhcConflictError("WITHDRAWAL_TX_EVIDENCE_MISMATCH")
            binding = await _load_admin_wallet_binding(
                db,
                admin=admin,
                wallet_binding_id=reserved_ref[1],
                require_primary=True,
            )
            _assert_claimed_sender_matches_binding(
                req.sender_wallet_address,
                binding_address=str(binding.wallet_address),
            )
            if not req.sender_wallet_address:
                raise EfhcConflictError("ADMIN_PAYOUT_SENDER_WALLET_REQUIRED")
            await AdminLogger.write(
                db,
                actor_global_id=admin.global_id,
                admin_id=admin.id,
                action="WITHDRAWAL_WALLET_SEND_CONFIRMED",
                entity="withdrawal",
                entity_id=withdrawal_id,
                details=(
                    f"payout_ref={persisted_payout_ref}; "
                    f"sender_wallet={binding.wallet_address}; "
                    f"wallet_provider={req.wallet_provider or binding.wallet_app or ''}; "
                    f"tx_hash={req.tx_hash or persisted_tx_hash}"
                ),
                required=True,
            )

        tg_id = int(row.tg_id)
        amount = d8(row.amount)
        # Если холд не был сделан — пытаемся восстановить.
        if not bool(row.hold_done):
            try:
                await debit_user_to_bank_nocommit(
                    db,
                    global_id=int(row.global_id),
                    amount=amount,
                    reason="withdraw_hold",
                    idempotency_key=f"{str(row.idempotency_key)}:hold",
                    meta={
                        "admin_id": admin.id,
                        "admin_role": admin.role,
                        "withdrawal_id": withdrawal_id,
                        "source": "withdraw_request_repair",
                    },
                )
                res = await db.execute(
                    text(
                        """
            UPDATE efhc_core.withdraw_requests
                        SET hold_done = TRUE,
                            updated_at = NOW() AT TIME ZONE 'UTC'
                        WHERE id = :wid
                          AND status = 'PENDING'"""
                    ),
                    {"wid": withdrawal_id},
                )
                if int(getattr(res, "rowcount", 0) or 0) == 0:
                    raise RuntimeError(
                        "withdraw hold repair marker race"
                    )
            except Exception as e:
                err_text = f"{type(e).__name__}: {e}"
                res = await db.execute(
                    text(
                        """
            UPDATE efhc_core.withdraw_requests
                        SET processing_idempotency_key = :ik,
                            error_message = :err,
                            updated_at = NOW() AT TIME ZONE 'UTC'
                        WHERE id = :wid
                          AND status = 'PENDING'"""
                    ),
                    {
                        "ik": req.idempotency_key,
                        "err": err_text[:500],
                        "wid": withdrawal_id,
                    },
                )
                if getattr(res, "rowcount", 0) == 0:
                    logger.warning(
                        (
                            "withdraw error update skipped "
                            "(not PENDING): wid=%s"
                        ),
                        withdrawal_id,
                    )
                await AdminLogger.write(
                    db,
                    actor_global_id=admin.global_id,
                    admin_id=admin.id,
                    action="WITHDRAWAL_ERROR",
                    entity="withdraw_request",
                    entity_id=withdrawal_id,
                    details=err_text,
                )
                msg = f"Не удалось выполнить холд по заявке: {err_text}"
                raise ValueError(msg) from e

        # Помечаем заявку как PAID.
        r_paid: Result = await db.execute(
            text("""
                UPDATE efhc_core.withdraw_requests 
                   SET status = 'PAID',
                       processing_idempotency_key = :ik,
                       tx_hash = COALESCE(:txh, tx_hash),
                       payout_ref = COALESCE(:pref, payout_ref),
                       error_message = NULL,
                       processed_at = NOW() AT TIME ZONE 'UTC'
                 WHERE id = :wid
                   AND status = 'PENDING'
                """),
            {
                "ik": req.idempotency_key,
                "txh": req.tx_hash,
                "pref": req.payout_ref,
                "wid": withdrawal_id,
            },
        )
        if int(getattr(r_paid, "rowcount", 0) or 0) == 0:
            await AdminLogger.write(
                db,
                actor_global_id=admin.global_id,
                admin_id=admin.id,
                action="WITHDRAWAL_PAID_FORBIDDEN",
                entity="withdrawal",
                entity_id=withdrawal_id,
                details="transition forbidden",
            )
            raise ValueError("Переход запрещён")

        amount_s = format_decimal_str(amount, EFHC_DECIMALS)
        details = (
            f"telegram_recipient={tg_id}; amount={amount_s}; "
            f"tx_hash={req.tx_hash or ''}; "
            f"payout_ref={req.payout_ref or ''}; "
            f"wallet_send_confirmed={req.wallet_send_confirmed}; "
            f"wallet_provider={req.wallet_provider or ''}; "
            f"sender_wallet={req.sender_wallet_address or ''}; "
            f"confirmation_mode={mode}; "
            f"manual_reason={manual_reason if mode == 'manual' else ''}"
        )
        await AdminLogger.write(
            db,
            actor_global_id=admin.global_id,
            admin_id=admin.id,
            action="WITHDRAWAL_PAID",
            entity="withdrawal",
            entity_id=withdrawal_id,
            details=details,
            required=True,
        )

        message = (
            f"Выплачен вывод # {withdrawal_id} пользователю {tg_id} "
            f"на сумму {amount_s} EFHC"
        )
        payload = {
            "withdrawal_id": withdrawal_id,
            "global_id": f"{int(row.global_id):010d}",
            "amount": amount_s,
            "tx_hash": req.tx_hash or "",
            "payout_ref": req.payout_ref or "",
            "wallet_send_confirmed": bool(req.wallet_send_confirmed),
            "wallet_provider": req.wallet_provider or "",
            "sender_wallet_address": req.sender_wallet_address or "",
            "confirmation_mode": mode,
            "manual_reason": manual_reason if mode == "manual" else "",
        }
        outcome_bundle = await build_withdraw_outcome_bundle(
            db,
            request_id=withdrawal_id,
            tg_id=tg_id,
            global_id=int(row.global_id),
            outcome_kind="success",
            manual_comment=req.comment_override,
            auto_translated=bool(req.comment_auto_translated),
        )
        outcome_bundle.metadata.update(
            {
                "status": WithdrawalStatus.PAID,
                "tx_hash": req.tx_hash or "",
                "payout_ref": req.payout_ref or "",
                "wallet_send_confirmed": bool(
                    req.wallet_send_confirmed
                ),
                "wallet_provider": req.wallet_provider or "",
                "sender_wallet_address": (
                    req.sender_wallet_address or ""
                ),
                "confirmation_mode": mode,
                "manual_reason": (
                    manual_reason if mode == "manual" else ""
                ),
                "telegram_delivery": "pending",
            }
        )
        await save_withdraw_outcome_event(
            db,
            bundle=outcome_bundle,
        )
        payload_json = json.dumps(payload, ensure_ascii=False)
        notification_id = await AdminNotifier.notify_generic(
            db,
            event="WITHDRAWAL_PAID",
            message=message,
            payload_json=payload_json,
            send_telegram=False,
        )
        await db.commit()
        await _deliver_withdraw_notifications_after_commit(
            db,
            bundle=outcome_bundle,
            notification_id=notification_id,
            event="WITHDRAWAL_PAID",
            message=message,
        )

        return {
            "ok": True,
            "status": WithdrawalStatus.PAID,
            "idempotency_key": req.idempotency_key,
            "tx_hash": req.tx_hash,
            "payout_ref": req.payout_ref,
            "wallet_send_confirmed": bool(req.wallet_send_confirmed),
            "wallet_provider": req.wallet_provider,
            "sender_wallet_address": req.sender_wallet_address,
            "confirmation_mode": mode,
            "outcome": {
                "request_id": outcome_bundle.request_id,
                "global_id": f"{int(outcome_bundle.global_id):010d}",
                "outcome_kind": outcome_bundle.outcome_kind,
                "locale": outcome_bundle.locale,
                "comment": {
                    "text": outcome_bundle.comment.text,
                    "template_key": outcome_bundle.comment.template_key,
                    "source": outcome_bundle.comment.source,
                    "locale": outcome_bundle.comment.locale,
                    "manual_override_used": (
                        outcome_bundle.comment.manual_override_used
                    ),
                    "auto_translated": (
                        outcome_bundle.comment.auto_translated
                    ),
                },
                "promo": (
                    None
                    if outcome_bundle.promo is None
                    else {
                        "enabled": outcome_bundle.promo.enabled,
                        "key": outcome_bundle.promo.key,
                        "title": outcome_bundle.promo.title,
                        "body": outcome_bundle.promo.body,
                        "cta_label": outcome_bundle.promo.cta_label,
                        "cta_url": outcome_bundle.promo.cta_url,
                        "source": outcome_bundle.promo.source,
                    }
                ),
                "top_zone_enabled": bool(outcome_bundle.promo),
                "metadata": outcome_bundle.metadata,
            },
        }

    @staticmethod
    async def record_payout_evidence(
        db: AsyncSession,
        *,
        withdrawal_id: int,
        req: WithdrawalApproveRequest,
        admin: AdminUser,
    ) -> dict[str, Any]:
        """Сохранить wallet-send evidence, не переводя заявку в PAID."""
        RBAC.require_role(admin, AdminRole.MODERATOR)
        if not req.idempotency_key.strip():
            raise ValueError("idempotency_key обязателен")
        payout_ref = str(req.payout_ref or "").strip()
        tx_hash = str(req.tx_hash or "").strip()
        if not req.wallet_send_confirmed or not (payout_ref or tx_hash):
            raise ValueError("WITHDRAWAL_WALLET_EVIDENCE_REQUIRED")
        row = (
            await db.execute(
                text(
                    """
                    SELECT id, global_id, amount, status, external_address,
                           payout_ref, tx_hash, processing_idempotency_key
                      FROM efhc_core.withdraw_requests
                     WHERE id = :wid
                     FOR UPDATE
                    """
                ),
                {"wid": withdrawal_id},
            )
        ).fetchone()
        if not row:
            raise ValueError("Заявка на вывод не найдена")
        if str(row.status) == WithdrawalStatus.PAID:
            return {
                "ok": True,
                "status": WithdrawalStatus.PAID,
                "payout_ref": row.payout_ref,
                "tx_hash": row.tx_hash,
                "evidence_only": True,
            }
        if str(row.status) != WithdrawalStatus.PENDING:
            raise EfhcConflictError("withdrawal is not pending")
        if row.payout_ref and payout_ref and str(row.payout_ref) != payout_ref:
            raise EfhcConflictError("payout evidence mismatch")
        if row.tx_hash and tx_hash and str(row.tx_hash) != tx_hash:
            raise EfhcConflictError("tx evidence mismatch")
        if tx_hash:
            tx_hash = _normalize_withdraw_tx_hash(tx_hash)
            await _claim_withdrawal_tx_hash(
                db,
                withdrawal_id=withdrawal_id,
                tx_hash=tx_hash,
            )
            await _verify_withdrawal_tx_onchain(
                tx_hash=tx_hash,
                recipient_address=str(row.external_address or ""),
                amount_efhc=d8(row.amount),
            )
        await db.execute(
            text(
                """
                UPDATE efhc_core.withdraw_requests
                   SET payout_ref = COALESCE(payout_ref, :payout_ref),
                       tx_hash = COALESCE(tx_hash, :tx_hash),
                       updated_at = NOW() AT TIME ZONE 'UTC'
                 WHERE id = :wid AND status = 'PENDING'
                """
            ),
            {
                "wid": withdrawal_id,
                "payout_ref": payout_ref or None,
                "tx_hash": tx_hash or None,
            },
        )
        await AdminLogger.write(
            db,
            actor_global_id=admin.global_id,
            admin_id=admin.id,
            action="WITHDRAWAL_PAYOUT_EVIDENCE",
            entity="withdrawal",
            entity_id=withdrawal_id,
            details=(
                f"payout_ref={payout_ref}; tx_hash={tx_hash}; "
                f"wallet_provider={req.wallet_provider or ''}; "
                f"sender_wallet={req.sender_wallet_address or ''}"
            ),
            required=True,
        )
        await db.commit()
        return {
            "ok": True,
            "status": WithdrawalStatus.PENDING,
            "payout_ref": payout_ref or row.payout_ref,
            "tx_hash": tx_hash or row.tx_hash,
            "evidence_only": True,
        }

    @staticmethod
    async def approve_withdrawal(
        db: AsyncSession,
        *,
        withdrawal_id: int,
        req: WithdrawalApproveRequest,
        admin: AdminUser,
    ) -> dict[str, Any]:
        """Compatibility alias: explicit mark-paid semantics, never approval-only."""
        return await WithdrawalsService.mark_withdrawal_paid(
            db, withdrawal_id=withdrawal_id, req=req, admin=admin
        )

    @staticmethod
    async def reject_withdrawal(
        db: AsyncSession,
        *,
        withdrawal_id: int,
        reason: str,
        idempotency_key: str,
        admin: AdminUser,
        comment_override: str | None = None,
        comment_auto_translated: bool = False,
    ) -> dict[str, Any]:
        """Отклоняет заявку на вывод EFHC с идемпотентностью."""
        RBAC.require_role(admin, AdminRole.MODERATOR)
        ik = str(idempotency_key).strip()
        if not ik:
            raise ValueError("idempotency_key обязателен")

        r_req: Result = await db.execute(
            text(
                """
                SELECT
                    id,
                    tg_id,
                    global_id,
                    amount,
                    status,
                    idempotency_key,
                    hold_done,
                    refund_done,
                    processing_idempotency_key
                FROM efhc_core.withdraw_requests
                WHERE id = :wid
                FOR UPDATE
                """
            ),
            {"wid": withdrawal_id},
        )
        row = r_req.fetchone()
        if not row:
            raise ValueError("Заявка на вывод не найдена")

        final_statuses = (
            WithdrawalStatus.PAID,
            WithdrawalStatus.REJECTED,
            WithdrawalStatus.CANCELED,
        )
        processing_ik = str(row.processing_idempotency_key or "")
        if row.status in final_statuses:
            if (
                row.status == WithdrawalStatus.REJECTED
                and processing_ik == ik
            ):
                return {
                    "ok": True,
                    "status": WithdrawalStatus.REJECTED,
                    "reason": reason,
                    "idempotency_key": ik,
                }
            raise EfhcConflictError("already processed")
        if processing_ik:
            payout_ref_row = (
                await db.execute(
                    text(
                        f"SELECT payout_ref FROM {SCHEMA_CORE}.withdraw_requests "
                        "WHERE id = :wid"
                    ),
                    {"wid": withdrawal_id},
                )
            ).scalar_one_or_none()
            if _parse_payout_reservation_ref(payout_ref_row) is not None:
                raise EfhcConflictError(
                    "WITHDRAWAL_PAYOUT_RESERVED_REJECT_FORBIDDEN"
                )
            if processing_ik == ik:
                return {
                    "ok": True,
                    "status": str(row.status),
                    "reason": reason,
                    "idempotency_key": ik,
                }
            raise EfhcConflictError(
                "withdrawal already processing with another key"
            )

        r_rej: Result = await db.execute(
            text(
                """
                UPDATE efhc_core.withdraw_requests
                   SET status = 'REJECTED',
                       processing_idempotency_key = :ik,
                       error_message = :reason,
                       processed_at = NOW() AT TIME ZONE 'UTC'
                 WHERE id = :wid
                   AND status = 'PENDING'
                RETURNING
                   tg_id,
                   global_id,
                   amount,
                   idempotency_key,
                   hold_done,
                   refund_done
                """
            ),
            {
                "ik": ik,
                "reason": reason[:500],
                "wid": withdrawal_id,
            },
        )
        row = r_rej.fetchone()
        if not row:
            await AdminLogger.write(
                db,
                actor_global_id=admin.global_id,
                admin_id=admin.id,
                action="WITHDRAWAL_REJECT_FORBIDDEN",
                entity="withdrawal",
                entity_id=withdrawal_id,
                details="transition forbidden",
            )
            raise ValueError("Переход запрещён")

        if bool(row.hold_done) and not bool(row.refund_done):
            await credit_user_from_bank_nocommit(
                db,
                global_id=int(row.global_id),
                amount=d8(row.amount),
                reason="withdraw_refund",
                idempotency_key=f"{str(row.idempotency_key)}:refund",
            )
            refund_marker = await db.execute(
                text(
                    """
                    UPDATE efhc_core.withdraw_requests
                       SET refund_done = TRUE,
                           updated_at = NOW() AT TIME ZONE 'UTC'
                     WHERE id = :wid
                       AND status = 'REJECTED'
                       AND hold_done = TRUE
                       AND refund_done = FALSE
                    """
                ),
                {"wid": withdrawal_id},
            )
            if int(getattr(refund_marker, "rowcount", 0) or 0) == 0:
                raise RuntimeError(
                    "withdraw refund marker race"
                )

        await AdminLogger.write(
            db,
            actor_global_id=admin.global_id,
            admin_id=admin.id,
            action="WITHDRAWAL_REJECT",
            entity="withdrawal",
            entity_id=withdrawal_id,
            details=reason,
            required=True,
        )
        outcome_bundle = await build_withdraw_outcome_bundle(
            db,
            request_id=withdrawal_id,
            tg_id=int(row.tg_id),
            global_id=int(row.global_id),
            outcome_kind="reject",
            manual_comment=(comment_override or reason),
            auto_translated=bool(comment_auto_translated),
        )
        outcome_bundle.metadata.update(
            {
                "status": WithdrawalStatus.REJECTED,
                "reason": reason,
                "telegram_delivery": "pending",
            }
        )
        await save_withdraw_outcome_event(
            db,
            bundle=outcome_bundle,
        )
        message = f"Отклонён вывод #{withdrawal_id}: {reason}"
        notification_id = await AdminNotifier.notify_generic(
            db,
            event="WITHDRAWAL_REJECT",
            message=message,
            send_telegram=False,
        )
        await db.commit()
        await _deliver_withdraw_notifications_after_commit(
            db,
            bundle=outcome_bundle,
            notification_id=notification_id,
            event="WITHDRAWAL_REJECT",
            message=message,
        )
        return {
            "ok": True,
            "status": WithdrawalStatus.REJECTED,
            "reason": reason,
            "idempotency_key": ik,
            "outcome": {
                "request_id": outcome_bundle.request_id,
                "global_id": f"{int(outcome_bundle.global_id):010d}",
                "outcome_kind": outcome_bundle.outcome_kind,
                "locale": outcome_bundle.locale,
                "comment": {
                    "text": outcome_bundle.comment.text,
                    "template_key": outcome_bundle.comment.template_key,
                    "source": outcome_bundle.comment.source,
                    "locale": outcome_bundle.comment.locale,
                    "manual_override_used": (
                        outcome_bundle.comment.manual_override_used
                    ),
                    "auto_translated": (
                        outcome_bundle.comment.auto_translated
                    ),
                },
                "promo": None,
                "top_zone_enabled": False,
                "metadata": outcome_bundle.metadata,
            },
        }

    # --------------------------------------------------------------
    # БЛОК 3. Бонусные выплаты EFHC (bonus_awards → бонусный баланс)
    # --------------------------------------------------------------

    @staticmethod
    async def list_bonus_awards(
        db: AsyncSession,
        filters: BonusAwardFilters,
    ) -> list[BonusAwardRecord]:
        """
        Возвращает legacy bonus_awards, если таблица есть.

        В активном каноне таблицы нет: возвращается пустой список.
        Фильтрация выполняется по resolved global_id, status, source
        и vip_only.
        """
        if not await _legacy_bonus_awards_table_exists(db):
            return []

        where = ["1=1"]
        params: dict[str, Any] = {
            "limit": filters.limit,
            "offset": filters.offset,
        }
        if filters.global_id is not None:
            where.append("u.global_id = :global_id")
            params["global_id"] = int(filters.global_id)
        if filters.status is not None:
            where.append("b.status = :st")
            params["st"] = filters.status
        if filters.source is not None:
            where.append("b.source = :src")
            params["src"] = filters.source
        if filters.vip_only:
            where.append("u.is_vip = TRUE")

        order = "DESC" if filters.sort_desc else "ASC"
        where_clause = " AND ".join(where)
        sql_tpl = """
            SELECT
                b.id,
                u.global_id,
                b.amount,
                b.status,
                b.source,
                b.created_at,
                b.processed_at,
                b.meta_json,
                COALESCE(u.is_vip, FALSE) AS is_vip
            FROM efhc_admin.bonus_awards b
            JOIN efhc_core.user_identities ui
              ON ui.provider = 'telegram'
             AND ui.provider_tenant = 'default'
             AND ui.provider_subject = CAST(b.tg_id AS TEXT)
             AND ui.status = 'active'
             AND ui.is_verified = TRUE
            JOIN efhc_core.users u ON u.global_id = ui.global_id
            WHERE {where_clause}
            ORDER BY b.id {order}
            LIMIT :limit OFFSET :offset
            """
        sql = text(
            sql_tpl.replace("efhc_admin", SCHEMA_ADMIN)
            .replace("efhc_core", SCHEMA_CORE)
            .replace("{where_clause}", where_clause)
            .replace("{order}", order)
        )
        r: Result = await db.execute(sql, params)
        out: list[BonusAwardRecord] = []
        for row in r.fetchall():
            created = row.created_at
            processed = getattr(row, "processed_at", None)
            created_iso = getattr(created, "isoformat", None)
            created_s = (
                created_iso() if callable(created_iso) else str(created)
            )
            iso = getattr(processed, "isoformat", None)
            processed_s = iso() if callable(iso) else None
            meta_raw = getattr(row, "meta_json", None)
            meta_json = str(meta_raw) if meta_raw is not None else None
            out.append(
                BonusAwardRecord(
                    id=int(row.id),
                    global_id=f"{int(row.global_id):010d}",
                    amount_efhc=str(row.amount),
                    status=str(row.status),
                    source=str(row.source),
                    created_at=created_s,
                    processed_at=processed_s,
                    meta_json=meta_json,
                    is_vip=bool(row.is_vip),
                )
            )
        return out

    @staticmethod
    async def process_bonus_award(
        db: AsyncSession,
        *,
        award_id: int,
        req: BonusAwardProcessRequest,
        admin: AdminUser,
    ) -> dict[str, Any]:
        """
        Выплачивает бонус EFHC по записи bonus_awards.

          • Требует статус PENDING или ERROR.
          • Использует credit_user_bonus_from_bank(...).
          • Обновляет статус bonus_awards на PAID и сохраняет ключ.
          • Идемпотентен по полю processing_idempotency_key.

        RBAC:
          • Минимум MODERATOR.
        """
        RBAC.require_role(admin, AdminRole.MODERATOR)
        await _ensure_legacy_bonus_awards_table(db)
        if not req.idempotency_key.strip():
            raise ValueError("idempotency_key обязателен")

        # Читаем запись
        r: Result = await db.execute(
            text(
                """
            SELECT
                    id,
                    ba.tg_id,
                    u.global_id,
                    ba.amount,
                    ba.status,
                    ba.processing_idempotency_key,
                    ba.source
                FROM efhc_admin.bonus_awards ba
                JOIN efhc_core.user_identities ui
                  ON ui.provider = 'telegram'
                 AND ui.provider_tenant = 'default'
                 AND ui.provider_subject = CAST(ba.tg_id AS TEXT)
                 AND ui.status = 'active'
                 AND ui.is_verified = TRUE
                JOIN efhc_core.users u ON u.global_id = ui.global_id
                WHERE ba.id = :aid
                FOR UPDATE"""
            ),
            {"aid": award_id},
        )
        row = r.fetchone()
        if not row:
            raise ValueError("Бонусная запись не найдена")

        final_statuses = (
            BonusAwardStatus.PAID,
            BonusAwardStatus.REJECTED,
        )
        if row.status in final_statuses:
            return {
                "ok": False,
                "status": str(row.status),
                "detail": "Бонус уже обработан",
            }

        # Идемпотентность
        if row.processing_idempotency_key:
            processing_ik = str(row.processing_idempotency_key)
            if processing_ik == req.idempotency_key:
                logger.info(
                    "process_bonus_award: idem=%s aid=%s",
                    req.idempotency_key,
                    award_id,
                )
                return {
                    "ok": True,
                    "status": str(row.status),
                    "idempotency_key": req.idempotency_key,
                }
            else:
                raise ValueError(
                    "Бонус уже обрабатывается с другим ключом"
                )

        tg_id = int(row.tg_id)
        amount = d8(row.amount)
        src = str(row.source)

        meta = {
            "admin_id": admin.id,
            "admin_role": admin.role,
            "award_id": award_id,
            "source": src,
        }

        owner_global_id = int(row.global_id)
        try:
            await credit_user_bonus_from_bank(
                db,
                global_id=owner_global_id,
                amount=amount,
                reason=f"bonus_award:{src}",
                idempotency_key=req.idempotency_key,
                meta=meta,
            )
        except Exception as e:
            err_text = f"{type(e).__name__}: {e}"
            logger.warning(
                "process_bonus_award: credit failed aid=%s tg=%s: %s",
                award_id,
                tg_id,
                err_text,
            )
            res = await db.execute(
                text(
                    """
            UPDATE efhc_admin.bonus_awards
                    SET status = 'ERROR',
                        processing_idempotency_key=:ik,
                        processed_at = NOW() AT TIME ZONE 'UTC'
                    WHERE id = :aid
                      AND status = 'PENDING'"""
                ),
                {"ik": req.idempotency_key, "aid": award_id},
            )
            if getattr(res, "rowcount", 0) == 0:
                logger.warning(
                    (
                        "BONUS_AWARD ERROR update skipped "
                        "(not PENDING): aid=%s"
                    ),
                    award_id,
                )
            await AdminLogger.write(
                db,
                actor_global_id=admin.global_id,
                admin_id=admin.id,
                action="BONUS_AWARD_ERROR",
                entity="bonus_awards",
                entity_id=award_id,
                details=err_text,
            )
            msg = f"Не удалось начислить бонус EFHC: {err_text}"
            raise ValueError(msg) from e

        res = await db.execute(
            text(
                """
            UPDATE efhc_admin.bonus_awards
                SET status = 'PAID',
                    processing_idempotency_key=:ik,
                    processed_at = NOW() AT TIME ZONE 'UTC'
                WHERE id = :aid
                  AND status = 'PENDING'"""
            ),
            {"ik": req.idempotency_key, "aid": award_id},
        )
        if getattr(res, "rowcount", 0) == 0:
            logger.warning(
                (
                    "BONUS_AWARD PAID update skipped "
                    "(not PENDING): aid=%s"
                ),
                award_id,
            )

        amount_s = format_decimal_str(amount, EFHC_DECIMALS)
        details = (
            f"global_id={int(row.global_id):010d}; "
            f"telegram_delivery_recipient={tg_id}; amount={amount_s}"
        )
        await AdminLogger.write(
            db,
            actor_global_id=admin.global_id,
            admin_id=admin.id,
            action="BONUS_AWARD_PAID",
            entity="bonus_awards",
            entity_id=award_id,
            details=details,
        )

        message = (
            f"Выплачен бонус {amount_s} EFHC аккаунту "
            f"{int(row.global_id):010d} (bonus)"
        )
        payload = {
            "award_id": award_id,
            "global_id": f"{int(row.global_id):010d}",
            "amount": amount_s,
            "source": src,
            "admin_id": admin.id,
        }
        outcome_bundle = await build_withdraw_outcome_bundle(
            db,
            request_id=award_id,
            tg_id=tg_id,
            global_id=int(row.global_id),
            outcome_kind="success",
            manual_comment=req.comment_override,
            auto_translated=bool(req.comment_auto_translated),
        )
        outcome_bundle.metadata.update(
            {
                "status": WithdrawalStatus.PAID,
                "tx_hash": req.tx_hash or "",
                "payout_ref": req.payout_ref or "",
                "wallet_send_confirmed": bool(
                    req.wallet_send_confirmed
                ),
                "wallet_provider": req.wallet_provider or "",
                "sender_wallet_address": (
                    req.sender_wallet_address or ""
                ),
            }
        )
        await save_withdraw_outcome_event(
            db,
            bundle=outcome_bundle,
        )
        payload_json = json.dumps(payload, ensure_ascii=False)
        await AdminNotifier.notify_generic(
            db,
            event="BONUS_AWARD_PAID",
            message=message,
            payload_json=payload_json,
        )

        return {
            "ok": True,
            "status": BonusAwardStatus.PAID,
            "idempotency_key": req.idempotency_key,
        }

    @staticmethod
    async def reject_bonus_award(
        db: AsyncSession,
        *,
        award_id: int,
        reason: str,
        admin: AdminUser,
    ) -> dict[str, Any]:
        """
        Отклоняет бонусную выплату (без движения средств).

        Используется, если запись bonus_awards создана ошибочно или
        больше не актуальна.
        """
        RBAC.require_role(admin, AdminRole.MODERATOR)
        await _ensure_legacy_bonus_awards_table(db)

        r: Result = await db.execute(
            text(
                """
            SELECT id, status
                FROM efhc_admin.bonus_awards
                WHERE id = :aid
                LIMIT 1"""
            ),
            {"aid": award_id},
        )
        row = r.fetchone()
        if not row:
            raise ValueError("Бонусная запись не найдена")

        final_statuses = (
            BonusAwardStatus.PAID,
            BonusAwardStatus.REJECTED,
        )
        if row.status in final_statuses:
            return {
                "ok": False,
                "status": str(row.status),
                "detail": "Бонус уже обработан",
            }

        res = await db.execute(
            text(
                """
            UPDATE efhc_admin.bonus_awards
                SET status = 'REJECTED',
                    processed_at = NOW() AT TIME ZONE 'UTC'
                WHERE id = :aid
                  AND status = 'PENDING'"""
            ),
            {"aid": award_id},
        )
        if getattr(res, "rowcount", 0) == 0:
            logger.warning(
                (
                    "BONUS_AWARD REJECTED update skipped "
                    "(not PENDING): aid=%s"
                ),
                award_id,
            )

        await AdminLogger.write(
            db,
            actor_global_id=admin.global_id,
            admin_id=admin.id,
            action="BONUS_AWARD_REJECT",
            entity="bonus_awards",
            entity_id=award_id,
            details=reason,
        )

        await AdminNotifier.notify_generic(
            db,
            event="BONUS_AWARD_REJECT",
            message=f"Отклонён бонус  # {award_id}: {reason}",
        )

        return {"ok": True, "status": BonusAwardStatus.REJECTED}


__all__ = [
    "WithdrawalStatus",
    "BonusAwardStatus",
    "WithdrawalFilters",
    "BonusAwardFilters",
    "WithdrawalRecord",
    "BonusAwardRecord",
    "WithdrawalApproveRequest",
    "BonusAwardProcessRequest",
    "WithdrawalsService",
    "LEGACY_BONUS_AWARDS_NO_ACTIVE_TABLE",
]
