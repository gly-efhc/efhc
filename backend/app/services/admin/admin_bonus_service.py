"""Административный обзор бонусных начислений по monetary SSOT.

Денежная authority для totals/history — ``efhc_core.efhc_transfers_log``.
Domain/shadow logs используются только как evidence и не определяют сумму денег.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

BonusSource = Literal["tasks", "referrals", "manual"]


class AdminBonusSummary(BaseModel):
    """Суммарные начисления по действующим источникам бонусов."""

    total_amount: str
    tasks_amount: str
    referrals_amount: str
    manual_amount: str
    total_count: int
    tasks_count: int
    referrals_count: int
    manual_count: int


class AdminBonusItem(BaseModel):
    """Одна запись человекопонятной истории бонусного начисления."""

    event_key: str
    source: BonusSource
    source_label: str
    global_id: str
    username: str | None = None
    amount: str
    reason: str
    created_at: str
    admin_global_id: str | None = None


class AdminBonusActivity(BaseModel):
    """Статистика и страница истории бонусных начислений."""

    ok: bool = True
    summary: AdminBonusSummary
    items: list[AdminBonusItem] = Field(default_factory=list)
    limit: int
    offset: int


_BONUS_SUMMARY_SQL = """
WITH bonus_events AS (
    SELECT
        CASE
            WHEN e.reason LIKE 'task_bonus:%' THEN 'tasks'
            WHEN e.reason IN ('referral_active_unit', 'referral_level_bonus')
                THEN 'referrals'
            ELSE 'manual'
        END::text AS source,
        e.id::bigint AS event_id,
        e.global_id::bigint AS global_id,
        u.username::text AS username,
        e.amount::numeric AS amount,
        COALESCE(NULLIF(e.reason, ''), 'Денежное бонусное начисление')::text AS reason,
        COALESCE(
            NULLIF(COALESCE(e.meta, '{}')::jsonb ->> 'admin_global_id', '')::bigint,
            aw.global_id
        )::bigint AS admin_global_id,
        e.created_at AS created_at
    FROM efhc_core.efhc_transfers_log AS e
    LEFT JOIN efhc_core.users AS u
      ON u.global_id = e.global_id
    LEFT JOIN efhc_admin.admin_whitelist AS aw
      ON aw.id = NULLIF(
          COALESCE(e.meta, '{}')::jsonb ->> 'admin_id',
          ''
      )::bigint
    WHERE e.system_entity IS NULL
      AND e.global_id IS NOT NULL
      AND e.direction = 'credit'
      AND e.balance_type = 'bonus'
      AND (
          e.reason LIKE 'task_bonus:%'
          OR e.reason IN ('referral_active_unit', 'referral_level_bonus')
          OR e.reason LIKE 'admin_manual_%'
          OR e.reason LIKE 'ADMIN_%'
          OR COALESCE(e.meta, '{}')::jsonb ->> 'source'
             = 'admin_manual_bank_transfer'
      )
)

SELECT
    COALESCE(SUM(amount), 0) AS total_amount,
    COALESCE(SUM(amount) FILTER (WHERE source = 'tasks'), 0) AS tasks_amount,
    COALESCE(SUM(amount) FILTER (WHERE source = 'referrals'), 0) AS referrals_amount,
    COALESCE(SUM(amount) FILTER (WHERE source = 'manual'), 0) AS manual_amount,
    COUNT(*)::bigint AS total_count,
    COUNT(*) FILTER (WHERE source = 'tasks')::bigint AS tasks_count,
    COUNT(*) FILTER (WHERE source = 'referrals')::bigint AS referrals_count,
    COUNT(*) FILTER (WHERE source = 'manual')::bigint AS manual_count
FROM bonus_events
WHERE (CAST(:global_id AS BIGINT) IS NULL OR global_id = :global_id)
  AND (CAST(:date_from AS TIMESTAMPTZ) IS NULL OR created_at >= :date_from)
  AND (CAST(:date_to AS TIMESTAMPTZ) IS NULL OR created_at <= :date_to)
"""


_BONUS_ITEMS_SQL = """
WITH bonus_events AS (
    SELECT
        CASE
            WHEN e.reason LIKE 'task_bonus:%' THEN 'tasks'
            WHEN e.reason IN ('referral_active_unit', 'referral_level_bonus')
                THEN 'referrals'
            ELSE 'manual'
        END::text AS source,
        e.id::bigint AS event_id,
        e.global_id::bigint AS global_id,
        u.username::text AS username,
        e.amount::numeric AS amount,
        COALESCE(NULLIF(e.reason, ''), 'Денежное бонусное начисление')::text AS reason,
        COALESCE(
            NULLIF(COALESCE(e.meta, '{}')::jsonb ->> 'admin_global_id', '')::bigint,
            aw.global_id
        )::bigint AS admin_global_id,
        e.created_at AS created_at
    FROM efhc_core.efhc_transfers_log AS e
    LEFT JOIN efhc_core.users AS u
      ON u.global_id = e.global_id
    LEFT JOIN efhc_admin.admin_whitelist AS aw
      ON aw.id = NULLIF(
          COALESCE(e.meta, '{}')::jsonb ->> 'admin_id',
          ''
      )::bigint
    WHERE e.system_entity IS NULL
      AND e.global_id IS NOT NULL
      AND e.direction = 'credit'
      AND e.balance_type = 'bonus'
      AND (
          e.reason LIKE 'task_bonus:%'
          OR e.reason IN ('referral_active_unit', 'referral_level_bonus')
          OR e.reason LIKE 'admin_manual_%'
          OR e.reason LIKE 'ADMIN_%'
          OR COALESCE(e.meta, '{}')::jsonb ->> 'source'
             = 'admin_manual_bank_transfer'
      )
)

SELECT
    source,
    event_id,
    global_id,
    username,
    amount,
    reason,
    admin_global_id,
    created_at
FROM bonus_events
WHERE (CAST(:global_id AS BIGINT) IS NULL OR global_id = :global_id)
  AND (CAST(:date_from AS TIMESTAMPTZ) IS NULL OR created_at >= :date_from)
  AND (CAST(:date_to AS TIMESTAMPTZ) IS NULL OR created_at <= :date_to)
  AND (:source = 'all' OR source = :source)
ORDER BY created_at DESC, event_id DESC
LIMIT :limit OFFSET :offset
"""


class AdminBonusesService:
    """Read-only сервис активной истории бонусов."""

    @staticmethod
    def _filter_params(
        *,
        global_id: int | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> dict[str, object]:
        return {
            "global_id": int(global_id) if global_id is not None else None,
            "date_from": date_from,
            "date_to": date_to,
        }

    @classmethod
    async def list_activity(
        cls,
        db: AsyncSession,
        *,
        source: str = "all",
        global_id: int | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> AdminBonusActivity:
        """Вернуть статистику и историю из активных источников бонусов."""

        source_clean = str(source or "all").strip().lower()
        if source_clean not in {"all", "tasks", "referrals", "manual"}:
            raise ValueError("Неизвестный источник бонусов")

        safe_limit = max(1, min(int(limit), 200))
        safe_offset = max(0, int(offset))
        params = cls._filter_params(
            global_id=global_id,
            date_from=date_from,
            date_to=date_to,
        )

        summary_sql = text(_BONUS_SUMMARY_SQL)
        summary_row = (await db.execute(summary_sql, params)).mappings().one()

        list_params = dict(params)
        list_params["source"] = source_clean
        list_params["limit"] = safe_limit
        list_params["offset"] = safe_offset

        items_sql = text(_BONUS_ITEMS_SQL)
        rows = (await db.execute(items_sql, list_params)).mappings().all()

        labels = {
            "tasks": "Задания",
            "referrals": "Рефералы",
            "manual": "Администратор",
        }
        items: list[AdminBonusItem] = []
        for row in rows:
            row_source = str(row["source"])
            admin_global = row.get("admin_global_id")
            items.append(
                AdminBonusItem(
                    event_key=f"{row_source}:{int(row['event_id'])}",
                    source=cast(BonusSource, row_source),
                    source_label=labels[row_source],
                    global_id=f"{int(row['global_id']):010d}",
                    username=(
                        str(row["username"])
                        if row.get("username") is not None
                        else None
                    ),
                    amount=str(row["amount"]),
                    reason=str(row["reason"]),
                    created_at=row["created_at"].isoformat(),
                    admin_global_id=(
                        f"{int(admin_global):010d}"
                        if admin_global is not None
                        else None
                    ),
                )
            )

        return AdminBonusActivity(
            summary=AdminBonusSummary(
                total_amount=str(summary_row["total_amount"]),
                tasks_amount=str(summary_row["tasks_amount"]),
                referrals_amount=str(summary_row["referrals_amount"]),
                manual_amount=str(summary_row["manual_amount"]),
                total_count=int(summary_row["total_count"] or 0),
                tasks_count=int(summary_row["tasks_count"] or 0),
                referrals_count=int(summary_row["referrals_count"] or 0),
                manual_count=int(summary_row["manual_count"] or 0),
            ),
            items=items,
            limit=safe_limit,
            offset=safe_offset,
        )


__all__ = [
    "AdminBonusActivity",
    "AdminBonusItem",
    "AdminBonusSummary",
    "AdminBonusesService",
]
