# backend/app/routes/admin_reports_routes.py
# =====================================================================
# Доменные административные отчёты для аналитики EFHC Bot.
#
# Канон:
# - только административные read-only GET endpoints;
# - никаких записей, idempotency creation или изменения балансов;
# - никаких synthetic/demo данных в runtime-ответах;
# - никаких персональных полей в payload отчёта;
# - только ограниченные реальные временные ряды из runtime truth tables.
# =====================================================================

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, cast

from app.core.config_core import get_settings
from app.core.sql_aliases_core import canon_schema
from app.core.utils_core import format_decimal_str
from app.deps import AuthContext, get_db, require_admin
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import TextClause

router = APIRouter(
    prefix="/admin/reports",
    tags=["admin-reports"],
)

_settings = get_settings()
CORE_SCHEMA = canon_schema(
    getattr(_settings, "DB_SCHEMA_CORE", "efhc_core") or "efhc_core"
)
Bucket = Literal["hour", "day"]
Domain = Literal["users", "bank", "panels", "withdrawals", "deposits"]


def _trusted_static_sql(query: str) -> TextClause:
    # Вызывающий код передаёт только статический SQL из canon_schema()
    # и локальных констант. Пользовательские значения остаются bind-параметрами.
    return text(query)


class AdminDomainReportTrendPoint(BaseModel):
    bucket: str
    value: float


class AdminBankPolicyOut(BaseModel):
    system_entity: Literal["BANK_EFHC"] = "BANK_EFHC"
    balance_key: Literal["EFHC_MAIN"] = "EFHC_MAIN"
    initial_balance: str = "5000000.00000000"
    negative_balance_allowed: bool = True
    p2p_allowed: bool = False
    bank_global_id: None = None
    bank_tg_id: None = None
    user_owner: Literal["global_id"] = "global_id"


class AdminDomainReportOut(BaseModel):
    ok: bool = True
    data_kind: Literal["real_timeseries"] = "real_timeseries"
    synthetic: bool = False
    domain: Domain
    range_hours: int
    generated_at: str
    snapshot: dict[str, float] = Field(default_factory=dict)
    policy: AdminBankPolicyOut | None = None
    trend: list[AdminDomainReportTrendPoint] = Field(
        default_factory=list
    )
    empty_reason: str | None = None


async def _set_statement_timeout(db: AsyncSession) -> None:
    await db.execute(text("SET LOCAL statement_timeout = '3000ms'"))


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if value is None:
        return ""
    return str(value)


def _num(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        formatted = format_decimal_str(
            Decimal(str(value)),
            decimals=8,
        )
        return float(cast(str, formatted))
    except Exception:
        try:
            return float(value)
        except Exception:
            return 0.0


def _snapshot(row: Mapping[str, Any] | None) -> dict[str, float]:
    if row is None:
        return {}
    return {str(k): _num(v) for k, v in row.items()}


def _trend(
    rows: list[Mapping[str, Any]],
) -> list[AdminDomainReportTrendPoint]:
    return [
        AdminDomainReportTrendPoint(
            bucket=_iso(row.get("bucket_ts")),
            value=_num(row.get("value")),
        )
        for row in rows
    ]


def _empty(points: list[AdminDomainReportTrendPoint]) -> str | None:
    return None if points else "no_rows_in_selected_range"


async def _first_mapping(
    db: AsyncSession,
    query: TextClause,
    params: dict[str, Any],
) -> Mapping[str, Any] | None:
    row = (await db.execute(query, params)).mappings().first()
    return dict(row) if row is not None else None


async def _all_mappings(
    db: AsyncSession,
    query: TextClause,
    params: dict[str, Any],
) -> list[Mapping[str, Any]]:
    rows = (await db.execute(query, params)).mappings().all()
    return [dict(row) for row in rows]


@router.get(
    "/users",
    response_model=AdminDomainReportOut,
    summary="Read-only user domain report",
)
async def reports_users(
    range_hours: int = Query(default=24, ge=1, le=720),
    bucket: Bucket = Query(default="hour"),
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(require_admin),
) -> AdminDomainReportOut:
    await _set_statement_timeout(db)
    snapshot_q = _trusted_static_sql(
        "select\n"  # nosec B608
        "  count(*)::numeric as total_users,\n"
        "  count(*) filter (\n"
        "    where created_at >= now() - "
        "make_interval(hours => :hours)\n"
        "  )::numeric as new_in_range,\n"
        "  count(*) filter (\n"
        "    where last_seen_at >= date_trunc('day', now())\n"
        "  )::numeric as active_today,\n"
        "  count(*) filter (\n"
        "    where exists (\n"
        f"      select 1 from {CORE_SCHEMA}.panels p\n"
        "      where p.global_id = users.global_id\n"
        "    )\n"
        "  )::numeric as with_panel,\n"
        "  count(*) filter (\n"
        "    where exists (\n"
        f"      select 1 from {CORE_SCHEMA}.wallet_bindings wb\n"
        "      where wb.global_id = users.global_id\n"
        "        and wb.is_active = true\n"
        "        and wb.proof_verified = true\n"
        "    )\n"
        "  )::numeric as with_wallet\n"
        f"from {CORE_SCHEMA}.users\n"
    )
    trend_q = _trusted_static_sql(
        "select\n"  # nosec B608
        "  date_trunc(:bucket, created_at) as bucket_ts,\n"
        "  count(*)::numeric as value\n"
        f"from {CORE_SCHEMA}.users\n"
        "where created_at >= now() - make_interval(hours => :hours)\n"
        "group by bucket_ts\n"
        "order by bucket_ts asc\n"
    )
    params = {"hours": int(range_hours), "bucket": bucket}
    snapshot = _snapshot(await _first_mapping(db, snapshot_q, params))
    trend = _trend(await _all_mappings(db, trend_q, params))
    return AdminDomainReportOut(
        domain="users",
        range_hours=int(range_hours),
        generated_at=datetime.now(UTC).isoformat(),
        snapshot=snapshot,
        trend=trend,
        empty_reason=_empty(trend),
    )


@router.get(
    "/bank",
    response_model=AdminDomainReportOut,
    summary="Read-only bank domain report",
)
async def reports_bank(
    range_hours: int = Query(default=24, ge=1, le=720),
    bucket: Bucket = Query(default="hour"),
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(require_admin),
) -> AdminDomainReportOut:
    await _set_statement_timeout(db)
    snapshot_q = _trusted_static_sql(
        "with bank as (\n"  # nosec B608
        "  select\n"
        "    coalesce(max(balance) filter "
        "(where key = 'EFHC_MAIN'), 0)::numeric\n"
        "      as bank_main_balance\n"
        f"  from {CORE_SCHEMA}.bank_balance\n"
        "), transfers as (\n"
        "  select\n"
        "    coalesce(sum(amount) filter "
        "(where direction = 'credit'), 0)::numeric\n"
        "      as credits_in_range,\n"
        "    coalesce(sum(amount) filter "
        "(where direction = 'debit'), 0)::numeric\n"
        "      as debits_in_range,\n"
        "    count(*) filter (where direction = 'credit')::numeric\n"
        "      as credit_events_in_range,\n"
        "    count(*) filter (where direction = 'debit')::numeric\n"
        "      as debit_events_in_range,\n"
        "    count(*)::numeric as total_events_in_range\n"
        f"  from {CORE_SCHEMA}.efhc_transfers_log\n"
        "  where system_entity = 'BANK_EFHC'\n"
        "    and created_at >= now() - make_interval(hours => :hours)\n"
        ")\n"
        "select\n"
        "  bank.bank_main_balance,\n"
        "  transfers.credits_in_range,\n"
        "  transfers.debits_in_range,\n"
        "  transfers.credit_events_in_range,\n"
        "  transfers.debit_events_in_range,\n"
        "  transfers.total_events_in_range,\n"
        "  (transfers.credits_in_range - transfers.debits_in_range)\n"
        "    ::numeric as net_flow_in_range\n"
        "from bank cross join transfers\n"
    )
    trend_q = _trusted_static_sql(
        "select\n"  # nosec B608
        "  date_trunc(:bucket, created_at) as bucket_ts,\n"
        "  count(*)::numeric as value\n"
        f"from {CORE_SCHEMA}.efhc_transfers_log\n"
        "where system_entity = 'BANK_EFHC'\n"
        "  and created_at >= now() - make_interval(hours => :hours)\n"
        "group by bucket_ts\n"
        "order by bucket_ts asc\n"
    )
    params = {"hours": int(range_hours), "bucket": bucket}
    snapshot = _snapshot(await _first_mapping(db, snapshot_q, params))
    trend = _trend(await _all_mappings(db, trend_q, params))
    return AdminDomainReportOut(
        domain="bank",
        range_hours=int(range_hours),
        generated_at=datetime.now(UTC).isoformat(),
        snapshot=snapshot,
        policy=AdminBankPolicyOut(),
        trend=trend,
        empty_reason=_empty(trend),
    )


@router.get(
    "/panels",
    response_model=AdminDomainReportOut,
    summary="Read-only panels domain report",
)
async def reports_panels(
    range_hours: int = Query(default=168, ge=1, le=2160),
    bucket: Bucket = Query(default="day"),
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(require_admin),
) -> AdminDomainReportOut:
    await _set_statement_timeout(db)
    snapshot_q = _trusted_static_sql(
        "select\n"  # nosec B608
        "  count(*)::numeric as total_panels,\n"
        "  count(*) filter (where is_active)::numeric\n"
        "    as active_panels,\n"
        "  count(*) filter (where not is_active or is_archived)"
        "::numeric\n"
        "    as archived_panels,\n"
        "  count(*) filter (\n"
        "    where created_at >= now() - "
        "make_interval(hours => :hours)\n"
        "  )::numeric as created_in_range,\n"
        "  count(*) filter (\n"
        "    where is_active and expires_at >= now()\n"
        "      and expires_at < now() + interval '7 days'\n"
        "  )::numeric as expiring_7d,\n"
        "  count(*) filter (\n"
        "    where is_active and expires_at >= now()\n"
        "      and expires_at < now() + interval '30 days'\n"
        "  )::numeric as expiring_30d,\n"
        "  count(*) filter (\n"
        "    where is_active and expires_at < now()\n"
        "  )::numeric as expired_but_active,\n"
        "  count(*) filter (\n"
        "    where is_active and expires_at is null\n"
        "  )::numeric as missing_expiry,\n"
        "  count(*) filter (\n"
        "    where is_active and now() - coalesce(activated_at, created_at)"
        " < interval '30 days'\n"
        "  )::numeric as active_age_under_30d,\n"
        "  count(*) filter (\n"
        "    where is_active and now() - coalesce(activated_at, created_at)"
        " >= interval '30 days'\n"
        "      and now() - coalesce(activated_at, created_at)"
        " < interval '120 days'\n"
        "  )::numeric as active_age_30_119d,\n"
        "  count(*) filter (\n"
        "    where is_active and now() - coalesce(activated_at, created_at)"
        " >= interval '120 days'\n"
        "  )::numeric as active_age_120d_plus,\n"
        "  coalesce(sum(generated_kwh), 0)::numeric as generated_kwh_total,\n"
        "  coalesce(sum(base_gen_per_sec) filter (where is_active), 0)::numeric"
        " as active_base_rate_total,\n"
        "  coalesce(avg(\n"
        "    extract(epoch from (\n"
        "      coalesce(archived_at, now()) -\n"
        "      coalesce(activated_at, created_at)\n"
        "    )) / 86400.0\n"
        "  ), 0)::numeric as avg_lifetime_days\n"
        f"from {CORE_SCHEMA}.panels\n"
    )
    trend_q = _trusted_static_sql(
        "select\n"  # nosec B608
        "  date_trunc(:bucket, created_at) as bucket_ts,\n"
        "  count(*)::numeric as value\n"
        f"from {CORE_SCHEMA}.panels\n"
        "where created_at >= now() - make_interval(hours => :hours)\n"
        "group by bucket_ts\n"
        "order by bucket_ts asc\n"
    )
    params = {"hours": int(range_hours), "bucket": bucket}
    snapshot = _snapshot(await _first_mapping(db, snapshot_q, params))
    trend = _trend(await _all_mappings(db, trend_q, params))
    return AdminDomainReportOut(
        domain="panels",
        range_hours=int(range_hours),
        generated_at=datetime.now(UTC).isoformat(),
        snapshot=snapshot,
        trend=trend,
        empty_reason=_empty(trend),
    )


@router.get(
    "/withdrawals",
    response_model=AdminDomainReportOut,
    summary="Read-only withdrawals domain report",
)
async def reports_withdrawals(
    range_hours: int = Query(default=168, ge=1, le=720),
    bucket: Bucket = Query(default="day"),
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(require_admin),
) -> AdminDomainReportOut:
    await _set_statement_timeout(db)
    snapshot_q = _trusted_static_sql(
        "select\n"  # nosec B608
        "  count(*)::numeric as total_count,\n"
        "  count(*) filter (where status = 'PENDING')::numeric\n"
        "    as pending_count,\n"
        "  count(*) filter (where status = 'PAID')::numeric\n"
        "    as paid_count,\n"
        "  count(*) filter (where status = 'REJECTED')::numeric\n"
        "    as rejected_count,\n"
        "  count(*) filter (where status = 'CANCELED')::numeric\n"
        "    as canceled_count,\n"
        "  coalesce(sum(amount) filter (\n"
        "    where status = 'PAID'\n"
        "      and coalesce(processed_at, created_at) >=\n"
        "        now() - make_interval(hours => :hours)\n"
        "  ), 0)::numeric as total_amount_paid_in_range\n"
        f"from {CORE_SCHEMA}.withdraw_requests\n"
    )
    trend_q = _trusted_static_sql(
        "select\n"  # nosec B608
        "  date_trunc(:bucket, created_at) as bucket_ts,\n"
        "  count(*)::numeric as value\n"
        f"from {CORE_SCHEMA}.withdraw_requests\n"
        "where created_at >= now() - make_interval(hours => :hours)\n"
        "group by bucket_ts\n"
        "order by bucket_ts asc\n"
    )
    params = {"hours": int(range_hours), "bucket": bucket}
    snapshot = _snapshot(await _first_mapping(db, snapshot_q, params))
    trend = _trend(await _all_mappings(db, trend_q, params))
    return AdminDomainReportOut(
        domain="withdrawals",
        range_hours=int(range_hours),
        generated_at=datetime.now(UTC).isoformat(),
        snapshot=snapshot,
        trend=trend,
        empty_reason=_empty(trend),
    )


@router.get(
    "/deposits",
    response_model=AdminDomainReportOut,
    summary="Read-only deposits domain report",
)
async def reports_deposits(
    range_hours: int = Query(default=24, ge=1, le=720),
    bucket: Bucket = Query(default="hour"),
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(require_admin),
) -> AdminDomainReportOut:
    await _set_statement_timeout(db)
    snapshot_q = _trusted_static_sql(
        "select\n"  # nosec B608
        "  count(*) filter (where status = 'PENDING')\n"
        "    ::numeric as pending_intents,\n"
        "  count(*) filter (where status = 'CONFIRMED')::numeric\n"
        "    as auto_credited,\n"
        "  count(*) filter (\n"
        "    where status in ("
        "'pending_manual', 'parsed_pending_mapping')\n"
        "  )::numeric as manual_review,\n"
        "  count(*) filter (where status like 'error%')::numeric\n"
        "    as error_count,\n"
        "  coalesce(sum(efhc_amount_d8) filter (\n"
        "    where status = 'CONFIRMED'\n"
        "      and updated_at >= now() - "
        "make_interval(hours => :hours)\n"
        "  ), 0)::numeric as total_credited_in_range\n"
        f"from {CORE_SCHEMA}.payment_intents\n"
    )
    trend_q = _trusted_static_sql(
        "select\n"  # nosec B608
        "  date_trunc(:bucket, created_at) as bucket_ts,\n"
        "  count(*)::numeric as value\n"
        f"from {CORE_SCHEMA}.payment_intents\n"
        "where created_at >= now() - make_interval(hours => :hours)\n"
        "group by bucket_ts\n"
        "order by bucket_ts asc\n"
    )
    params = {"hours": int(range_hours), "bucket": bucket}
    snapshot = _snapshot(await _first_mapping(db, snapshot_q, params))
    trend = _trend(await _all_mappings(db, trend_q, params))
    return AdminDomainReportOut(
        domain="deposits",
        range_hours=int(range_hours),
        generated_at=datetime.now(UTC).isoformat(),
        snapshot=snapshot,
        trend=trend,
        empty_reason=_empty(trend),
    )
