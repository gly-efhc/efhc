"""Единая глобально упорядоченная история профиля с keyset-пагинацией."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from app.utils.cursor_codec import decode_cursor, encode_cursor
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

PROFILE_HISTORY_PAGE_SIZE: Final[int] = 50
PROFILE_HISTORY_EXPORT_BATCH_SIZE: Final[int] = 500


@dataclass(frozen=True, slots=True)
class ProfileHistoryRecord:
    """Нормализованная логическая операция из разнородных источников."""

    id: int
    source: str
    kind: str
    occurred_at: datetime
    status: str | None
    direction: str | None
    balance_type: str | None
    amount_efhc: str | None
    amount_asset: str | None
    asset: str | None
    reason: str | None
    recipient_address: str | None
    source_rank: int
    executed_at: datetime | None = None
    panel_public_id: str | None = None


@dataclass(frozen=True, slots=True)
class ProfileHistoryPage:
    """Одна keyset-страница общего порядка."""

    items: tuple[ProfileHistoryRecord, ...]
    next_cursor: str | None


def _parse_cursor(cursor: str | None) -> tuple[datetime, int, int] | None:
    if not cursor:
        return None
    payload = decode_cursor(cursor)
    try:
        ts = datetime.fromisoformat(str(payload["ts"]))
        rank = int(payload["rank"])
        source_id = int(payload["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("PROFILE_HISTORY_CURSOR_INVALID") from exc
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError("PROFILE_HISTORY_CURSOR_INVALID")
    return ts.astimezone(UTC), rank, source_id


def _make_cursor(record: ProfileHistoryRecord) -> str:
    return str(
        encode_cursor(
            {
                "ts": record.occurred_at.astimezone(UTC).isoformat(),
                "rank": int(record.source_rank),
                "id": int(record.id),
            }
        )
    )


async def list_profile_history_page(
    db: AsyncSession,
    *,
    global_id: int,
    cursor: str | None = None,
    page_size: int = PROFILE_HISTORY_PAGE_SIZE,
    category: str = "all",
    include_panel_purchases: bool = False,
) -> ProfileHistoryPage:
    """Вернуть единую страницу без схемы 50+50+50."""

    if category not in {"all", "purchases", "exchange", "withdraw", "bonuses", "panels"}:
        raise ValueError("PROFILE_HISTORY_CATEGORY_INVALID")

    limit = int(page_size)
    if limit < 1 or limit > PROFILE_HISTORY_EXPORT_BATCH_SIZE:
        raise ValueError("PROFILE_HISTORY_PAGE_SIZE_INVALID")
    parsed = _parse_cursor(cursor)
    cursor_ts = parsed[0] if parsed else None
    cursor_rank = parsed[1] if parsed else None
    cursor_id = parsed[2] if parsed else None

    query = text(
        """
        WITH panel_legs AS (
            SELECT l.id, l.amount, l.balance_type, l.created_at,
                   m.j->>'idempotency_key' AS purchase_key, p.public_id
            FROM efhc_core.efhc_transfers_log l
            CROSS JOIN LATERAL (
               SELECT CASE WHEN pg_input_is_valid(l.meta, 'jsonb')
                           THEN CAST(l.meta AS jsonb) END AS j
            ) m
            JOIN efhc_core.panels p ON p.global_id = l.global_id
                AND p.id = CASE WHEN (m.j->'panels_created_ids'->>0) ~ '^[1-9][0-9]{0,17}$'
                     THEN CAST(m.j->'panels_created_ids'->>0 AS bigint) END
                AND p.public_id = m.j->'panels_public_ids'->>0
            WHERE :include_panel_purchases
              AND l.global_id = :global_id
              AND l.reason = 'panel_activation' AND l.direction = 'debit'
              AND m.j->>'qty' = '1'
              AND m.j->'panels_created_ids' = jsonb_build_array(p.id)
              AND m.j->'panels_public_ids' = jsonb_build_array(p.public_id)
              AND m.j->>'global_id' = CAST(l.global_id AS text)
              AND l.idempotency_key = (m.j->>'idempotency_key') || ':' || l.balance_type
              AND p.public_id ~ '^PNL-[0-9]{8}$' AND p.public_id <> 'PNL-00000000'
        ), panel_purchases AS (
            SELECT max(id) AS row_id, array_agg(id) AS source_ids,
                   sum(amount) AS total, min(public_id) AS public_id, count(*) AS leg_count
            FROM panel_legs GROUP BY purchase_key
            HAVING sum(amount) = 100 AND count(*) = count(DISTINCT balance_type)
                 AND count(DISTINCT public_id) = 1 AND min(created_at) = max(created_at)
        ), panel_purchase_members AS (
            SELECT pp.*, unnest(pp.source_ids) AS member_id FROM panel_purchases pp
        ), unified AS (
            SELECT
                t.id AS source_id,
                50::integer AS source_rank,
                'ledger'::text AS source,
                CASE
                    WHEN t.reason = 'exchange_kwh_to_efhc'
                    THEN 'exchange'
                    ELSE 'balance_transfer'
                END::text AS kind,
                t.created_at AS occurred_at,
                NULL::text AS status,
                t.direction::text AS direction,
                CASE WHEN pp.leg_count > 1 THEN NULL ELSE t.balance_type END::text AS balance_type,
                coalesce(pp.total,t.amount)::text AS amount_efhc,
                NULL::text AS amount_asset,
                CASE
                    WHEN pp.leg_count > 1 THEN 'EFHC'
                    WHEN t.balance_type = 'bonus' THEN 'EFHCb'
                    ELSE 'EFHCm'
                END::text AS asset,
                t.reason::text AS reason,
                NULL::text AS recipient_address,
                t.created_at AS executed_at,
                pp.public_id AS panel_public_id
            FROM efhc_core.efhc_transfers_log t
            LEFT JOIN panel_purchase_members pp ON pp.member_id=t.id
            WHERE t.global_id = :global_id
              AND (pp.row_id IS NULL OR pp.row_id=t.id)
              AND t.reason NOT IN (
                  'withdraw_hold',
                  'withdraw_refund',
                  'withdraw_reject_refund'
              )

            UNION ALL

            SELECT
                w.id,
                40::integer,
                'withdraw_request'::text,
                'withdraw_request'::text,
                w.created_at,
                w.status::text,
                NULL::text,
                'main'::text,
                w.amount::text,
                NULL::text,
                'EFHCm'::text,
                'withdraw_request'::text,
                w.external_address::text,
                CASE WHEN w.status = 'PAID' THEN w.processed_at
                     ELSE NULL END AS executed_at,
                NULL::text AS panel_public_id
            FROM efhc_core.withdraw_requests w
            WHERE w.global_id = :global_id

        ), categorized AS (
            SELECT unified.*,
                CASE
                    WHEN kind = 'exchange' OR POSITION('exchange' IN LOWER(COALESCE(reason, ''))) > 0 THEN 'exchange'
                    WHEN source = 'withdraw_request' OR POSITION('withdraw' IN LOWER(COALESCE(reason, ''))) > 0 THEN 'withdraw'
                    WHEN POSITION('panel' IN LOWER(COALESCE(reason, ''))) > 0 THEN 'panels'
                    WHEN balance_type = 'bonus'
                         OR POSITION('bonus' IN LOWER(COALESCE(reason, ''))) > 0
                         OR POSITION('referral' IN LOWER(COALESCE(reason, ''))) > 0
                         OR POSITION('task' IN LOWER(COALESCE(reason, ''))) > 0
                         OR POSITION('ad_' IN LOWER(COALESCE(reason, ''))) > 0 THEN 'bonuses'
                    WHEN source IN ('shop_order', 'payment_intent')
                         OR POSITION('shop' IN LOWER(COALESCE(reason, ''))) > 0
                         OR POSITION('payment' IN LOWER(COALESCE(reason, ''))) > 0
                         OR POSITION('deposit' IN LOWER(COALESCE(reason, ''))) > 0
                         OR POSITION('purchase' IN LOWER(COALESCE(reason, ''))) > 0 THEN 'purchases'
                    ELSE 'other'
                END AS category
            FROM unified
        )
        SELECT
            source_id,
            source_rank,
            source,
            kind,
            occurred_at,
            status,
            direction,
            balance_type,
            amount_efhc,
            amount_asset,
            asset,
            reason,
            recipient_address,
            executed_at,
            panel_public_id
        FROM categorized
        WHERE (
            :category = 'all'
            OR (category = :category
                AND (:category <> 'withdraw' OR source = 'withdraw_request'))
        )
          AND (
            CAST(:cursor_ts AS timestamptz) IS NULL
            OR occurred_at < CAST(:cursor_ts AS timestamptz)
            OR (
                occurred_at = CAST(:cursor_ts AS timestamptz)
                AND source_rank < CAST(:cursor_rank AS integer)
            )
            OR (
                occurred_at = CAST(:cursor_ts AS timestamptz)
                AND source_rank = CAST(:cursor_rank AS integer)
                AND source_id < CAST(:cursor_id AS bigint)
            )
        )
        ORDER BY occurred_at DESC, source_rank DESC, source_id DESC
        LIMIT :limit_plus_one
        """
    )
    rows = (
        await db.execute(
            query,
            {
                "global_id": int(global_id),
                "include_panel_purchases": include_panel_purchases,
                "category": category,
                "cursor_ts": cursor_ts,
                "cursor_rank": cursor_rank,
                "cursor_id": cursor_id,
                "limit_plus_one": limit + 1,
            },
        )
    ).all()
    has_more = len(rows) > limit
    selected = rows[:limit]
    records: list[ProfileHistoryRecord] = []
    for row in selected:
        occurred_at = row[4]
        if not isinstance(occurred_at, datetime):
            raise RuntimeError("PROFILE_HISTORY_TIMESTAMP_INVALID")
        executed_at = row[13]
        if executed_at is not None and (
            not isinstance(executed_at, datetime) or executed_at.utcoffset() is None
        ):
            raise RuntimeError("PROFILE_HISTORY_EXECUTION_TIMESTAMP_INVALID")
        records.append(
            ProfileHistoryRecord(
                id=int(row[0]),
                source_rank=int(row[1]),
                source=str(row[2]),
                kind=str(row[3]),
                occurred_at=occurred_at.astimezone(UTC),
                status=str(row[5]) if row[5] is not None else None,
                direction=str(row[6]) if row[6] is not None else None,
                balance_type=(
                    str(row[7]) if row[7] is not None else None
                ),
                amount_efhc=(
                    str(row[8]) if row[8] is not None else None
                ),
                amount_asset=(
                    str(row[9]) if row[9] is not None else None
                ),
                asset=str(row[10]) if row[10] is not None else None,
                reason=str(row[11]) if row[11] is not None else None,
                recipient_address=(str(row[12]) if row[12] is not None else None),
                executed_at=executed_at.astimezone(UTC) if executed_at is not None else None,
                panel_public_id=str(row[14]) if row[14] is not None else None,
            )
        )
    next_cursor = _make_cursor(records[-1]) if has_more and records else None
    return ProfileHistoryPage(items=tuple(records), next_cursor=next_cursor)


__all__ = [
    "PROFILE_HISTORY_EXPORT_BATCH_SIZE",
    "PROFILE_HISTORY_PAGE_SIZE",
    "ProfileHistoryPage",
    "ProfileHistoryRecord",
    "list_profile_history_page",
]
