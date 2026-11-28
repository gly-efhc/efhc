from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.identity.types import (
    global_id_from_database,
    global_id_to_database,
    parse_global_id,
)
from app.lib.time import utcnow
from app.services.financial_execution_window import (
    require_external_financial_execution,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class TxHashSettlementClaim:
    """Результат глобального claim одной on-chain транзакции."""

    acquired: bool
    same_claim: bool
    existing_purpose: str | None = None
    existing_intent_id: int | None = None
    existing_order_id: int | None = None
    existing_global_id: str | None = None

    @property
    def can_continue(self) -> bool:
        """Разрешить только новый или точный идемпотентный claim."""
        return bool(self.acquired or self.same_claim)


async def claim_tx_hash_settlement(
    db: AsyncSession,
    *,
    tx_hash: str,
    purpose: str,
    global_id: str,
    trusted_operation_at: datetime | None,
    server_first_seen_at: datetime | None,
    intent_id: int | None = None,
    order_id: int | None = None,
) -> TxHashSettlementClaim:
    """Атомарно заявить единственное settlement-право на tx_hash.

    Таблица ``tx_hash_locks`` является глобальным on-chain settlement
    lock для watcher, PaymentIntent, direct deposit и Admin recovery.
    Разные бизнес-idempotency keys могут существовать, но один tx_hash
    не может породить два независимых финансовых settlement. Повтор
    точного того же claim допускается только как read-through к уже
    существующей бизнес-идемпотентности.
    """
    raw_hash = str(tx_hash or "").strip()
    raw_purpose = str(purpose or "").strip()
    if not raw_hash:
        raise ValueError("tx_hash обязателен для settlement claim")
    if not raw_purpose:
        raise ValueError("purpose обязателен для settlement claim")

    time_decision = require_external_financial_execution(
        trusted_operation_at=trusted_operation_at,
        server_first_seen_at=server_first_seen_at,
    )
    owner_db = global_id_to_database(parse_global_id(global_id))
    insert_query = text(
        """
        INSERT INTO efhc_core.tx_hash_locks (
            tx_hash, purpose, intent_id, order_id, global_id,
            trusted_operation_at, server_first_seen_at, created_at
        ) VALUES (
            :tx_hash, :purpose, :intent_id, :order_id, :global_id,
            :trusted_operation_at, :server_first_seen_at, :created_at
        )
        ON CONFLICT (tx_hash) DO NOTHING
        """
    )
    result = await db.execute(
        insert_query,
        {
            "tx_hash": raw_hash,
            "purpose": raw_purpose,
            "intent_id": (int(intent_id) if intent_id is not None else None),
            "order_id": (int(order_id) if order_id is not None else None),
            "global_id": owner_db,
            "trusted_operation_at": time_decision.trusted_operation_at,
            "server_first_seen_at": time_decision.server_first_seen_at,
            "created_at": utcnow(),
        },
    )
    if bool(getattr(result, "rowcount", 0)):
        return TxHashSettlementClaim(acquired=True, same_claim=False)

    existing = (
        (
            await db.execute(
                text(
                    """
                    SELECT purpose, intent_id, order_id, global_id,
                           trusted_operation_at, server_first_seen_at
                      FROM efhc_core.tx_hash_locks
                     WHERE tx_hash = :tx_hash
                    """
                ),
                {"tx_hash": raw_hash},
            )
        )
        .mappings()
        .first()
    )
    if existing is None:
        return TxHashSettlementClaim(acquired=False, same_claim=False)

    existing_global_id = str(
        global_id_from_database(existing["global_id"])
    )
    existing_intent = (
        int(existing["intent_id"])
        if existing.get("intent_id") is not None
        else None
    )
    existing_order = (
        int(existing["order_id"])
        if existing.get("order_id") is not None
        else None
    )
    same_claim = bool(
        str(existing.get("purpose") or "") == raw_purpose
        and existing_global_id == str(parse_global_id(global_id))
        and existing_intent
        == (int(intent_id) if intent_id is not None else None)
        and existing_order
        == (int(order_id) if order_id is not None else None)
        and str(existing.get("trusted_operation_at") or "")
        == str(time_decision.trusted_operation_at or "")
        and str(existing.get("server_first_seen_at") or "")
        == str(time_decision.server_first_seen_at or "")
    )
    return TxHashSettlementClaim(
        acquired=False,
        same_claim=same_claim,
        existing_purpose=str(existing.get("purpose") or "") or None,
        existing_intent_id=existing_intent,
        existing_order_id=existing_order,
        existing_global_id=existing_global_id,
    )


async def acquire_tx_hash_lock(
    db: AsyncSession,
    *,
    tx_hash: str,
    purpose: str,
    intent_id: int,
    global_id: str,
    trusted_operation_at: datetime | None,
    server_first_seen_at: datetime | None,
    order_id: int | None = None,
) -> bool:
    """Compatibility helper для PaymentIntent exact-new claim.

    Новый общий runtime, которому нужен direct/admin settlement, использует
    ``claim_tx_hash_settlement``. Этот helper сохранён, чтобы не ломать
    PaymentIntent compatibility surface и не создавать вторую реализацию.
    """
    claim = await claim_tx_hash_settlement(
        db,
        tx_hash=tx_hash,
        purpose=purpose,
        intent_id=int(intent_id),
        global_id=global_id,
        trusted_operation_at=trusted_operation_at,
        server_first_seen_at=server_first_seen_at,
        order_id=order_id,
    )
    return bool(claim.acquired)
