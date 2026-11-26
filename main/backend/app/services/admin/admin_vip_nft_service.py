"""Административный VIP/NFT-контур без ручного назначения VIP.

VIP определяется только фактическим владением NFT на подтверждённом TON-кошельке.
Заявки на ручную выдачу VIP NFT остаются ShopOrder(type='NFT') и не
дублируются отдельной таблицей или второй заявкой.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal

from app.services import nft_check_service, shop_service
from app.services.admin.admin_logging import AdminLogger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def check_user_vip_nft_now(
    db: AsyncSession,
    *,
    global_id: int,
    actor_global_id: int,
) -> dict[str, Any]:
    """Принудительно обновить VIP/Admin NFT для одного global_id."""

    wallet = await nft_check_service.NftCheckService.get_wallet_for_user(
        db,
        int(global_id),
    )
    result = await nft_check_service.check_user_vip_once(
        db,
        global_id=int(global_id),
        force_refresh=True,
    )
    if not wallet:
        # Каноническая проверка уже синхронизировала is_vip=False:
        # отсутствие подтверждённого TON-кошелька не оставляет старый VIP.
        await AdminLogger.write(
            db,
            actor_global_id=int(actor_global_id),
            action="vip_nft_recheck",
            entity="user",
            entity_id=int(global_id),
            details="wallet_missing; vip=false; admin_nft=false",
        )
        await db.commit()
        return {
            "ok": True,
            "state": "wallet_missing",
            "global_id": f"{int(global_id):010d}",
            "is_vip": False,
            "has_admin_nft": False,
            "message": "TON-кошелёк не подключён. VIP не активен.",
        }

    if result is None:
        await db.rollback()
        return {
            "ok": False,
            "state": "check_failed",
            "global_id": f"{int(global_id):010d}",
            "is_vip": False,
            "has_admin_nft": False,
            "message": "Не удалось проверить NFT. Повторите проверку позже.",
        }

    await AdminLogger.write(
        db,
        actor_global_id=int(actor_global_id),
        action="vip_nft_recheck",
        entity="user",
        entity_id=int(global_id),
        details=(
            f"vip={bool(result.is_vip)}; "
            f"admin_nft={bool(result.has_admin_nft)}"
        ),
    )
    await db.commit()
    return {
        "ok": True,
        "state": "vip_active" if result.is_vip else "vip_inactive",
        "global_id": f"{int(global_id):010d}",
        "is_vip": bool(result.is_vip),
        "has_admin_nft": bool(result.has_admin_nft),
        "checked_at": result.checked_at.isoformat(),
        "message": (
            "VIP NFT найден. Статус обновлён."
            if result.is_vip
            else "VIP NFT не найден. Статус обновлён."
        ),
    }


async def check_all_vip_nft_now(
    db: AsyncSession,
    *,
    actor_global_id: int,
) -> dict[str, Any]:
    """Принудительно проверить всех пользователей с TON-кошельками."""

    result = await nft_check_service.check__all__users_once(
        db,
        force_refresh=True,
    )
    await AdminLogger.write(
        db,
        actor_global_id=int(actor_global_id),
        action="vip_nft_recheck_all",
        entity="vip_nft",
        entity_id=None,
        details=(
            f"checked={int(result.get('total', 0))}; "
            f"changed={int(result.get('changed', 0))}"
        ),
    )
    await db.commit()
    return {
        "ok": True,
        "checked": int(result.get("total", 0)),
        "changed": int(result.get("changed", 0)),
        "message": "Проверка VIP и NFT завершена.",
    }


async def list_vip_nft_requests(
    db: AsyncSession,
    *,
    limit: int = 50,
    cursor: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Вернуть Shop NFT-заказы как единую очередь ручной выдачи."""

    page = await shop_service.admin_list_orders(
        db,
        limit=int(limit),
        cursor=cursor,
        status=status,
        item_type="NFT",
        global_id=None,
    )
    counts_result = await db.execute(
        text(
            """
            SELECT status, COUNT(*) AS cnt
              FROM efhc_core.shop_orders
             WHERE type = 'NFT'
             GROUP BY status
            """
        )
    )
    counts = {
        str(row.status): int(row.cnt or 0)
        for row in counts_result.fetchall()
    }
    return {
        **page,
        "counts": {
            "total": sum(counts.values()),
            "waiting": int(counts.get("PAID_PENDING_MANUAL", 0)),
            "issued": int(counts.get("APPROVED", 0)),
            "rejected": int(counts.get("REJECTED", 0)),
        },
    }


async def decide_vip_nft_request(
    db: AsyncSession,
    *,
    order_id: int,
    decision: Literal["issued", "rejected"],
    reason: str,
    actor_global_id: int,
    admin_id: int | None = None,
    admin_role: str | None = None,
    delivery_tx_hash: str | None = None,
) -> dict[str, Any]:
    """Завершить ручную выдачу NFT или отклонить её с обязательной причиной."""

    row = (
        await db.execute(
            text(
                """
                SELECT id, global_id, type, status, tx_hash, extra
                  FROM efhc_core.shop_orders
                 WHERE id = :order_id
                 FOR UPDATE
                """
            ),
            {"order_id": int(order_id)},
        )
    ).mappings().first()
    if row is None:
        raise ValueError("NFT_REQUEST_NOT_FOUND")
    if str(row.get("type") or "") != "NFT":
        raise ValueError("NFT_REQUEST_TYPE_REQUIRED")

    current = str(row.get("status") or "")
    target = "APPROVED" if decision == "issued" else "REJECTED"
    if current == target:
        return {
            "ok": True,
            "order_id": int(order_id),
            "status": current,
            "already_decided": True,
        }
    if current != "PAID_PENDING_MANUAL":
        raise ValueError("NFT_REQUEST_NOT_WAITING_FOR_DECISION")

    note = str(reason or "").strip()
    if not note:
        raise ValueError("NFT_REQUEST_REASON_REQUIRED")
    delivery_hash = str(delivery_tx_hash or "").strip() or None
    if decision == "rejected" and delivery_hash:
        raise ValueError("NFT_REQUEST_REJECTED_DELIVERY_HASH_FORBIDDEN")

    extra = row.get("extra") or {}
    if not isinstance(extra, dict):
        extra = {}
    now = datetime.now(UTC).isoformat()
    extra = dict(extra)
    extra["nft_delivery"] = {
        "decision": decision,
        "reason": note,
        "delivery_tx_hash": delivery_hash,
        "decided_by_global_id": f"{int(actor_global_id):010d}",
        "decided_at": now,
    }

    await db.execute(
        text(
            """
            UPDATE efhc_core.shop_orders
               SET status = :status,
                   extra = CAST(:extra AS jsonb),
                   fulfilled_at = CASE
                       WHEN :status = 'APPROVED'
                       THEN COALESCE(fulfilled_at, NOW())
                       ELSE fulfilled_at
                   END,
                   updated_at = NOW()
             WHERE id = :order_id
            """
        ),
        {
            "order_id": int(order_id),
            "status": target,
            "extra": json.dumps(extra, ensure_ascii=False),
        },
    )
    await AdminLogger.write(
        db,
        actor_global_id=int(actor_global_id),
        action=(
            "vip_nft_issued"
            if decision == "issued"
            else "vip_nft_rejected"
        ),
        entity="shop_order",
        entity_id=int(order_id),
        admin_id=admin_id,
        details=(
            f"global_id={int(row['global_id']):010d}; "
            f"reason={note}; delivery_tx={delivery_hash or '-'}"
        ),
        meta={"admin_role": str(admin_role or "")},
        required=True,
    )
    await db.commit()
    return {
        "ok": True,
        "order_id": int(order_id),
        "global_id": f"{int(row['global_id']):010d}",
        "status": target,
        "already_decided": False,
        "message": (
            "Выдача VIP NFT подтверждена."
            if decision == "issued"
            else "Заявка отклонена. Оплата не возвращается автоматически."
        ),
    }
