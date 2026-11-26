"""Wallet bindings service for TonConnect.

SSOT rules:
- Wallet ownership and read-side queries use canonical ``global_id``.
- Telegram proof/connect remains provider-specific.
  It requires ``tg_id``.
- wallet_connected := at least one active verified wallet binding.
- /wallets/connect requires Idempotency-Key and a verified
  TonConnect proof bound to tg_id/domain/payload/address.

This module is infrastructure for wallet bindings only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import cast

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.identity.types import (
    global_id_from_database,
    global_id_to_database,
    parse_global_id,
)
from app.lib.time import utcnow
from app.services import transactions_service as tx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
settings = get_settings()
CORE_SCHEMA: str = getattr(settings, "DB_SCHEMA_CORE", "efhc_core")

WALLET_PROOF_REPLAY_TTL = timedelta(hours=24)
WALLET_CONNECT_IDEMPOTENCY_TTL = timedelta(days=7)


def _global_id_db(global_id: str) -> int:
    """Явная граница: внешний десятизначный global_id -> BIGINT БД."""
    return cast(int, global_id_to_database(parse_global_id(global_id)))


# ПОСТОЯННЫЙ ФАСАД СОВМЕСТИМОСТИ — НЕ ИСПОЛЬЗОВАТЬ В НОВОМ КОДЕ.
# Денежная логика остаётся в transactions_service; фасад сохранён, потому что
# удаление этого import seam уже вызывало регрессии. Business owner — только
# canonical десятизначный global_id.
async def credit_user_from_bank(
    db: AsyncSession,
    *,
    global_id: str,
    amount_efhc=None,
    amount=None,
    reason: str,
    idempotency_key: str,
    meta=None,
):
    return await tx.credit_user_from_bank(
        db,
        global_id=_global_id_db(global_id),
        amount_efhc=amount_efhc,
        amount=amount,
        reason=str(reason),
        idempotency_key=str(idempotency_key),
        meta=meta,
    )


# ПОСТОЯННЫЕ АЛИАСЫ СОВМЕСТИМОСТИ — НЕ ИСПОЛЬЗОВАТЬ В НОВОМ КОДЕ.
# Исторические импорты сохранены для совместимости; новые callers используют
# статусы canonical watcher/reconciliation service.
STATUS_CREDITED = "credited"
STATUS_ERROR_SYS = "error_retry"

# ---------------------------------------------------------------------
# ---------------------------------------------------------------------


class WalletConflict(Exception):
    pass


class InvalidWalletAddress(Exception):
    pass


class WalletProofRequired(Exception):
    pass


class WalletProofReplay(Exception):
    pass


def normalize_wallet_address(raw: str) -> str:
    """Return EFHC canonical TON address for wallet ownership."""
    from app.lib.ton_address import (
        TonAddressError,
        canonicalize_ton_address,
    )

    addr = str(raw or "").strip()
    if not addr:
        raise InvalidWalletAddress("INVALID_WALLET_ADDRESS")
    try:
        return cast(str, canonicalize_ton_address(addr))
    except TonAddressError as err:
        raise InvalidWalletAddress("INVALID_WALLET_ADDRESS") from err


@dataclass(slots=True)
class WalletBindingOut:
    id: int
    wallet_address: str
    wallet_app: str | None
    is_primary: bool
    is_active: bool
    proof_verified: bool
    created_at: str


async def list_wallets(
    db: AsyncSession,
    *,
    global_id: str,
) -> list[WalletBindingOut]:
    """Вернуть bindings по canonical ``global_id``."""
    rows = (
        await db.execute(
            text(
                """
                SELECT id,
                       wallet_address,
                       wallet_app,
                       is_primary,
                       is_active,
                       proof_verified,
                       created_at
                  FROM efhc_core.wallet_bindings
                 WHERE global_id = :global_id
                 ORDER BY is_primary DESC, id DESC
                """
            ),
            {"global_id": _global_id_db(global_id)},
        )
    ).mappings().all()
    return [
        WalletBindingOut(
            id=int(row["id"]),
            wallet_address=str(row["wallet_address"]),
            wallet_app=(
                str(row["wallet_app"])
                if row["wallet_app"]
                else None
            ),
            is_primary=bool(row["is_primary"]),
            is_active=bool(row["is_active"]),
            proof_verified=bool(row["proof_verified"]),
            created_at=str(row["created_at"]),
        )
        for row in rows
    ]


async def get_verified_active_wallet(
    db: AsyncSession,
    *,
    global_id: str,
    wallet_id: int,
) -> WalletBindingOut | None:
    """Разрешить выбранный wallet только внутри canonical owner boundary."""
    row = (
        await db.execute(
            text(
                """
                SELECT id, wallet_address, wallet_app, is_primary,
                       is_active, proof_verified, created_at
                  FROM efhc_core.wallet_bindings
                 WHERE id = :wallet_id
                   AND global_id = :global_id
                   AND is_active = true
                   AND proof_verified = true
                 LIMIT 1
                """
            ),
            {
                "wallet_id": int(wallet_id),
                "global_id": _global_id_db(global_id),
            },
        )
    ).mappings().first()
    if row is None:
        return None
    return WalletBindingOut(
        id=int(row["id"]),
        wallet_address=str(row["wallet_address"]),
        wallet_app=(str(row["wallet_app"]) if row["wallet_app"] else None),
        is_primary=bool(row["is_primary"]),
        is_active=bool(row["is_active"]),
        proof_verified=bool(row["proof_verified"]),
        created_at=str(row["created_at"]),
    )


async def has_active_wallet(
    db: AsyncSession,
    *,
    global_id: str,
) -> bool:
    """Проверить verified active binding canonical owner."""
    result = await db.execute(
        text(
            """
            SELECT 1
              FROM efhc_core.wallet_bindings
             WHERE global_id = :global_id
               AND is_active = true
               AND proof_verified = true
             LIMIT 1
            """
        ),
        {"global_id": _global_id_db(global_id)},
    )
    return bool(result.first())


def _proof_token_hash(payload_token: str) -> str:
    token = str(payload_token or "").strip()
    if not token:
        raise WalletProofRequired("TONCONNECT_PROOF_REQUIRED")
    return sha256(token.encode("utf-8")).hexdigest()


async def _ensure_verified_proof_not_used(
    db: AsyncSession,
    *,
    proof_payload_hash: str,
) -> None:
    """Запретить replay в 24h security window и освободить stale marker."""

    cutoff = utcnow() - WALLET_PROOF_REPLAY_TTL
    await db.execute(
        text("""
            DELETE FROM efhc_core.wallet_proof_token_uses
             WHERE proof_payload_hash = :proof_hash
               AND created_at < :cutoff
            """),
        {"proof_hash": proof_payload_hash, "cutoff": cutoff},
    )
    row = (
        await db.execute(
            text("""
                SELECT 1
                  FROM efhc_core.wallet_proof_token_uses
                 WHERE proof_payload_hash = :proof_hash
                   AND created_at >= :cutoff
                 LIMIT 1
                """),
            {"proof_hash": proof_payload_hash, "cutoff": cutoff},
        )
    ).first()
    if row:
        raise WalletProofReplay("TONCONNECT_PROOF_REPLAY")


async def _mark_verified_proof_single_use(
    db: AsyncSession,
    *,
    global_id: str,
    provider_tg_id: int,
    wallet_address: str,
    proof_payload_hash: str,
    idempotency_key: str,
) -> None:
    res = await db.execute(
        text("""
            INSERT INTO efhc_core.wallet_proof_token_uses
                (global_id, tg_id, wallet_address,
                 proof_payload_hash, idempotency_key, created_at)
            VALUES
                (:global_id, :tg_id, :addr,
                 :proof_hash, :ik, :now)
            ON CONFLICT (proof_payload_hash) DO NOTHING
            RETURNING id
            """),
        {
            "global_id": _global_id_db(global_id),
            "tg_id": int(provider_tg_id),
            "addr": wallet_address,
            "proof_hash": proof_payload_hash,
            "ik": idempotency_key,
            "now": utcnow(),
        },
    )
    if res.first() is None:
        raise WalletProofReplay("TONCONNECT_PROOF_REPLAY")


async def connect_wallet(
    db: AsyncSession,
    *,
    global_id: str,
    provider_tg_id: int,
    address: str,
    wallet_app: str | None,
    idempotency_key: str,
    verified_proof_payload_token: str,
    verified_proof_source: str,
) -> dict:
    """Bind verified TON address to the canonical account owner."""
    logger.info(
        "wallet.connect attempt",
        extra={
            "audit__schema__version": "v1",
            "global_id": _global_id_db(global_id),
            "event": "wallet_connect",
            "result": "attempt",
        },
    )
    if not idempotency_key:
        raise ValueError("IDEMPOTENCY_REQUIRED")
    proof_hash = _proof_token_hash(verified_proof_payload_token)
    proof_source = str(verified_proof_source or "").strip()
    if not proof_source:
        raise WalletProofRequired("TONCONNECT_PROOF_REQUIRED")

    idk_cutoff = utcnow() - WALLET_CONNECT_IDEMPOTENCY_TTL
    await db.execute(
        text("""
            DELETE FROM efhc_core.wallet_connect_idempotency AS idem
             WHERE idem.global_id = :global_id
               AND idem.idempotency_key = :ik
               AND (
                   idem.created_at < :cutoff
                   OR NOT EXISTS (
                       SELECT 1
                         FROM efhc_core.wallet_bindings wb
                        WHERE wb.id = idem.wallet_id
                          AND wb.global_id = idem.global_id
                          AND wb.wallet_address = idem.wallet_address
                          AND wb.is_active = TRUE
                          AND wb.proof_verified = TRUE
                   )
               )
            """),
        {
            "global_id": _global_id_db(global_id),
            "ik": idempotency_key,
            "cutoff": idk_cutoff,
        },
    )
    idk_row = (
        await db.execute(
            text("""
                SELECT idem.wallet_id, idem.wallet_address
                  FROM efhc_core.wallet_connect_idempotency AS idem
                  JOIN efhc_core.wallet_bindings AS wb
                    ON wb.id = idem.wallet_id
                   AND wb.global_id = idem.global_id
                   AND wb.wallet_address = idem.wallet_address
                 WHERE idem.global_id = :global_id
                   AND idem.idempotency_key = :ik
                   AND idem.created_at >= :cutoff
                   AND wb.is_active = TRUE
                   AND wb.proof_verified = TRUE
                 LIMIT 1
                """),
            {
                "global_id": _global_id_db(global_id),
                "ik": idempotency_key,
                "cutoff": idk_cutoff,
            },
        )
    ).mappings().first()
    if idk_row:
        return {
            "wallet_id": int(idk_row["wallet_id"]),
            "wallet_address": str(idk_row["wallet_address"]),
            "is_connected": True,
        }

    addr = normalize_wallet_address(address)
    await _ensure_verified_proof_not_used(
        db, proof_payload_hash=proof_hash
    )
    owner = (
        await db.execute(
            text("""
                SELECT global_id
                  FROM efhc_core.wallet_bindings
                 WHERE wallet_address = :addr
                 LIMIT 1
                """),
            {"addr": addr},
        )
    ).first()
    if owner and str(global_id_from_database(owner[0])) != global_id:
        raise WalletConflict("WALLET_CONFLICT")

    row = (
        await db.execute(
            text("""
                SELECT id, is_active
                  FROM efhc_core.wallet_bindings
                 WHERE wallet_address = :addr
                   AND global_id = :global_id
                 LIMIT 1
                """),
            {"addr": addr, "global_id": _global_id_db(global_id)},
        )
    ).mappings().first()
    now = utcnow()
    if row:
        wallet_id = int(row["id"])
        await db.execute(
            text("""
                UPDATE efhc_core.wallet_bindings
                   SET is_active = true,
                       proof_verified = true,
                       proof_verified_at = :now,
                       proof_payload_hash = :proof_hash,
                       proof_source = :proof_source,
                       tg_id = :tg_id,
                       wallet_app = COALESCE(:wallet_app, wallet_app),
                       updated_at = :now
                 WHERE id = :id
                   AND global_id = :global_id
                """),
            {
                "id": wallet_id,
                "global_id": _global_id_db(global_id),
                "tg_id": int(provider_tg_id),
                "wallet_app": wallet_app,
                "proof_hash": proof_hash,
                "proof_source": proof_source,
                "now": now,
            },
        )
    else:
        wallet_id = int(
            (
                await db.execute(
                    text("""
                        INSERT INTO efhc_core.wallet_bindings
                            (global_id, tg_id, wallet_address,
                             wallet_app, is_primary, is_active,
                             proof_verified, proof_verified_at,
                             proof_payload_hash, proof_source,
                             created_at, updated_at)
                        VALUES
                            (:global_id, :tg_id, :addr,
                             :wallet_app, false, true,
                             true, :now, :proof_hash, :proof_source,
                             :now, :now)
                        RETURNING id
                        """),
                    {
                        "global_id": _global_id_db(global_id),
                        "tg_id": int(provider_tg_id),
                        "addr": addr,
                        "wallet_app": wallet_app,
                        "proof_hash": proof_hash,
                        "proof_source": proof_source,
                        "now": now,
                    },
                )
            ).scalar_one()
        )

    await _mark_verified_proof_single_use(
        db,
        global_id=global_id,
        provider_tg_id=provider_tg_id,
        wallet_address=addr,
        proof_payload_hash=proof_hash,
        idempotency_key=idempotency_key,
    )
    has_primary = (
        await db.execute(
            text("""
                SELECT 1
                  FROM efhc_core.wallet_bindings
                 WHERE global_id = :global_id
                   AND is_primary = true
                   AND is_active = true
                   AND proof_verified = true
                 LIMIT 1
                """),
            {"global_id": _global_id_db(global_id)},
        )
    ).first()
    if not has_primary:
        await _make_primary_tx(
            db, global_id=global_id, wallet_id=wallet_id
        )
    await _save_connect_idempotency(
        db,
        global_id=global_id,
        provider_tg_id=provider_tg_id,
        idempotency_key=idempotency_key,
        wallet_id=wallet_id,
        wallet_address=addr,
    )
    await db.commit()
    return {
        "wallet_id": wallet_id,
        "wallet_address": addr,
        "is_connected": True,
    }


async def _save_connect_idempotency(
    db: AsyncSession,
    *,
    global_id: str,
    provider_tg_id: int,
    idempotency_key: str,
    wallet_id: int,
    wallet_address: str,
) -> None:
    await db.execute(
        text("""
            INSERT INTO efhc_core.wallet_connect_idempotency
                (global_id, tg_id, idempotency_key,
                 wallet_id, wallet_address, created_at)
            VALUES
                (:global_id, :tg_id, :ik,
                 :wallet_id, :addr, :now)
            ON CONFLICT (global_id, idempotency_key) DO NOTHING
            """),
        {
            "global_id": _global_id_db(global_id),
            "tg_id": int(provider_tg_id),
            "ik": idempotency_key,
            "wallet_id": wallet_id,
            "addr": wallet_address,
            "now": utcnow(),
        },
    )


async def make_primary(
    db: AsyncSession,
    *,
    global_id: str,
    wallet_id: int,
) -> None:
    await _make_primary_tx(
        db, global_id=global_id, wallet_id=wallet_id
    )
    await db.commit()


async def _clear_vip_if_no_wallet_source(
    db: AsyncSession,
    *,
    global_id: str,
) -> bool:
    """Снять VIP, только если не осталось допустимого TON wallet source."""

    gid = _global_id_db(global_id)
    source_result = await db.execute(
        text("""
            SELECT EXISTS (
                SELECT 1
                FROM efhc_core.wallet_bindings wb
                WHERE wb.global_id = :global_id
                  AND wb.is_active = TRUE
                  AND wb.proof_verified = TRUE
                  AND wb.wallet_address IS NOT NULL
                  AND LENGTH(TRIM(wb.wallet_address)) > 0
            ) AS has_verified_binding
            """
        ),
        {"global_id": gid},
    )
    row = source_result.fetchone()
    if row is not None and bool(row.has_verified_binding):
        return False

    from app.services.energy_service import (
        set_user_vip_with_energy_checkpoint,
    )

    return cast(
        bool,
        await set_user_vip_with_energy_checkpoint(
            db,
            global_id=gid,
            new_is_vip=False,
        ),
    )


async def admin_reset_wallet_bindings(
    db: AsyncSession,
    *,
    global_id: str,
) -> int:
    result = await db.execute(
        text("""
            UPDATE efhc_core.wallet_bindings
               SET is_active = false,
                   is_primary = false,
                   updated_at = :now
             WHERE global_id = :global_id
               AND (is_active = true OR is_primary = true)
            """),
        {"global_id": _global_id_db(global_id), "now": utcnow()},
    )
    await _clear_vip_if_no_wallet_source(db, global_id=global_id)
    return int(getattr(result, "rowcount", 0) or 0)


async def deactivate_wallet(
    db: AsyncSession,
    *,
    global_id: str,
    wallet_id: int,
) -> None:
    """Compatibility name: explicit detach физически освобождает binding."""

    gid = _global_id_db(global_id)
    now = utcnow()
    deleted = (
        await db.execute(
            text("""
                DELETE FROM efhc_core.wallet_bindings
                 WHERE id = :id
                   AND global_id = :global_id
                RETURNING wallet_address, is_primary
                """),
            {"id": int(wallet_id), "global_id": gid},
        )
    ).mappings().first()
    if deleted is None:
        await db.commit()
        return

    wallet_address = str(deleted["wallet_address"])
    await db.execute(
        text("""
            DELETE FROM efhc_core.wallet_connect_idempotency
             WHERE global_id = :global_id
               AND (wallet_id = :wallet_id OR wallet_address = :wallet_address)
            """),
        {
            "global_id": gid,
            "wallet_id": int(wallet_id),
            "wallet_address": wallet_address,
        },
    )

    if bool(deleted["is_primary"]):
        await db.execute(
            text("""
                UPDATE efhc_core.wallet_bindings
                   SET is_primary = TRUE, updated_at = :now
                 WHERE id = (
                     SELECT id
                       FROM efhc_core.wallet_bindings
                      WHERE global_id = :global_id
                        AND is_active = TRUE
                        AND proof_verified = TRUE
                      ORDER BY created_at ASC, id ASC
                      LIMIT 1
                 )
                """),
            {"global_id": gid, "now": now},
        )

    await _clear_vip_if_no_wallet_source(db, global_id=global_id)
    await db.commit()


async def _make_primary_tx(
    db: AsyncSession,
    *,
    global_id: str,
    wallet_id: int,
) -> None:
    now = utcnow()
    await db.execute(
        text("""
            UPDATE efhc_core.wallet_bindings
               SET is_primary = false,
                   updated_at = :now
             WHERE global_id = :global_id
            """),
        {"global_id": _global_id_db(global_id), "now": now},
    )
    result = await db.execute(
        text("""
            UPDATE efhc_core.wallet_bindings
               SET is_primary = true,
                   is_active = true,
                   updated_at = :now
             WHERE id = :id
               AND global_id = :global_id
               AND proof_verified = true
            """),
        {
            "id": wallet_id,
            "global_id": _global_id_db(global_id),
            "now": now,
        },
    )
    if int(getattr(result, "rowcount", 0) or 0) != 1:
        raise ValueError("Подтверждённый wallet binding владельца не найден")


# -------------------------------------------------------------------
# ПОСТОЯННЫЙ ФАСАД СОВМЕСТИМОСТИ — НЕ ИСПОЛЬЗОВАТЬ В НОВОМ КОДЕ.
# Истина подтверждения — payment_reconciliation_service.confirm_payment_intent;
# этот вход сохранён как совместимый seam после cleanup-регрессий.
# -------------------------------------------------------------------


async def _confirm_payment_intent(
    db: AsyncSession,
    *,
    intent_id: int,
    global_id: str,
    provider_tg_id: int | None,
    purpose: str,
    payload: str,
    tx_hash: str,
    amount_asset,
    asset: str,
    external_amount_atomic: int | str | None = None,
    external_decimals: int | None = None,
    to_address: str,
    trusted_operation_at: datetime | None = None,
    server_first_seen_at: datetime | None = None,
) -> str:
    from .watcher_service import _confirm_payment_intent as _confirm

    result = await _confirm(
        db,
        intent_id=int(intent_id),
        global_id=global_id,
        provider_tg_id=(
            int(provider_tg_id) if provider_tg_id is not None else None
        ),
        purpose=str(purpose),
        payload=str(payload),
        tx_hash=str(tx_hash),
        amount_asset=amount_asset,
        asset=str(asset),
        external_amount_atomic=external_amount_atomic,
        external_decimals=external_decimals,
        to_address=str(to_address),
        trusted_operation_at=trusted_operation_at,
        server_first_seen_at=server_first_seen_at,
        credit_user_from_bank_fn=credit_user_from_bank,
    )
    return str(result)
