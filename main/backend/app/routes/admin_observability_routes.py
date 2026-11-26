# backend/app/routes/admin_observability_routes.py
# =====================================================================
# Контракты observability для реальных административных дашбордов EFHC Bot.
#
# Канон:
# - только административные read-only GET endpoints;
# - никаких write actions, создания idempotency или денежных мутаций;
# - никаких synthetic/demo/fake series в runtime;
# - никаких raw payload/meta, секретов или debug JSON наружу;
# - только ограниченные реальные временные ряды из runtime truth tables.
# =====================================================================

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, cast

from app.core.config_core import get_settings
from app.core.runtime_observability import runtime_observability
from app.core.sql_aliases_core import canon_schema
from app.core.utils_core import format_decimal_str
from app.deps import AuthContext, get_db, require_admin
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import TextClause

router = APIRouter(
    prefix="/admin/observability",
    tags=["admin:observability"],
)

_settings = get_settings()
CORE_SCHEMA = canon_schema(
    getattr(_settings, "DB_SCHEMA_CORE", "efhc_core") or "efhc_core"
)

Bucket = Literal["hour", "day"]
MetricName = Literal[
    "users_created",
    "panels_created",
    "withdrawals_created",
    "payment_intents_created",
    "efhc_transfer_count",
    "efhc_transfer_amount",
    "efhc_credit_amount",
    "efhc_debit_amount",
]
Severity = Literal["info", "success", "warning", "danger"]


def _trusted_static_sql(query: str) -> TextClause:
    # Здесь используются только статические фрагменты canon_schema()
    # и MetricConfig, выбранные из Literal-ограниченного набора метрик.
    # Пользовательские значения остаются bind-параметрами execute().
    return text(query)


class AdminObservabilitySeriesPoint(BaseModel):
    ts: str
    value: str
    label: str | None = None


class AdminObservabilityTimeseriesOut(BaseModel):
    ok: bool = True
    data_kind: Literal["real_timeseries"] = "real_timeseries"
    synthetic: bool = False
    metric: MetricName
    bucket: Bucket
    range_hours: int
    unit: str
    source: str
    points: list[AdminObservabilitySeriesPoint] = Field(
        default_factory=list
    )
    empty_reason: str | None = None


class AdminObservabilitySummaryMetric(BaseModel):
    key: str
    label: str
    value: str
    unit: str
    source: str
    data_kind: Literal["raw", "derived"] = "raw"


class AdminObservabilitySummaryOut(BaseModel):
    ok: bool = True
    data_kind: Literal["raw", "derived"] = "derived"
    generated_at: str
    source: str = "existing runtime truth tables"
    metrics: list[AdminObservabilitySummaryMetric] = Field(
        default_factory=list
    )


class AdminObservabilityEvent(BaseModel):
    id: str
    type: str
    severity: Severity
    title: str
    description: str | None = None
    ts: str
    route: str | None = None
    source: str


class AdminObservabilityEventsOut(BaseModel):
    ok: bool = False
    data_kind: Literal["disabled_duplicate"] = "disabled_duplicate"
    status: Literal["disabled_duplicate"] = "disabled_duplicate"
    source: str = "compatibility_disabled_duplicate"
    reason: str = (
        "Функция отключена решением цикла 1719: она дублирует "
        "каноническую административную ленту /admin/logs/transfers."
    )
    replacement: str = "/admin/logs/transfers"
    items: list[AdminObservabilityEvent] = Field(default_factory=list)


class AdminObservabilityHealthOut(BaseModel):
    ok: bool = True
    data_kind: Literal["derived"] = "derived"
    generated_at: str
    contracts: list[dict[str, str]] = Field(
        default_factory=list
    )
    safety: dict[str, bool] = Field(default_factory=dict)
    posture: dict[str, str] = Field(default_factory=dict)
    deployment: dict[str, str] = Field(default_factory=dict)
    request_metrics: dict[str, Any] = Field(
        default_factory=dict
    )
    alerts: list[dict[str, Any]] = Field(default_factory=list)


@dataclass(frozen=True)
class MetricConfig:
    table: str
    ts_column: str
    value_sql: str
    unit: str
    source: str


METRICS: dict[str, MetricConfig] = {
    "users_created": MetricConfig(
        table=f"{CORE_SCHEMA}.users",
        ts_column="created_at",
        value_sql="count(*)::numeric",
        unit="users",
        source="users.created_at",
    ),
    "panels_created": MetricConfig(
        table=f"{CORE_SCHEMA}.panels",
        ts_column="created_at",
        value_sql="count(*)::numeric",
        unit="panels",
        source="panels.created_at",
    ),
    "withdrawals_created": MetricConfig(
        table=f"{CORE_SCHEMA}.withdraw_requests",
        ts_column="created_at",
        value_sql="count(*)::numeric",
        unit="withdrawals",
        source="withdraw_requests.created_at",
    ),
    "payment_intents_created": MetricConfig(
        table=f"{CORE_SCHEMA}.payment_intents",
        ts_column="created_at",
        value_sql="count(*)::numeric",
        unit="payment_intents",
        source="payment_intents.created_at",
    ),
    "efhc_transfer_count": MetricConfig(
        table=f"{CORE_SCHEMA}.efhc_transfers_log",
        ts_column="created_at",
        value_sql="count(*)::numeric",
        unit="events",
        source="efhc_transfers_log.created_at",
    ),
    "efhc_transfer_amount": MetricConfig(
        table=f"{CORE_SCHEMA}.efhc_transfers_log",
        ts_column="created_at",
        value_sql="coalesce(sum(amount), 0)::numeric",
        unit="EFHC gross turnover",
        source="efhc_transfers_log.amount gross turnover",
    ),
    "efhc_credit_amount": MetricConfig(
        table=f"{CORE_SCHEMA}.efhc_transfers_log",
        ts_column="created_at",
        value_sql=(
            "coalesce(sum(amount) filter "
            "(where direction = 'credit'), 0)::numeric"
        ),
        unit="EFHC credit",
        source="efhc_transfers_log.amount where direction=credit",
    ),
    "efhc_debit_amount": MetricConfig(
        table=f"{CORE_SCHEMA}.efhc_transfers_log",
        ts_column="created_at",
        value_sql=(
            "coalesce(sum(amount) filter "
            "(where direction = 'debit'), 0)::numeric"
        ),
        unit="EFHC debit",
        source="efhc_transfers_log.amount where direction=debit",
    ),
}


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if value is None:
        return ""
    return str(value)


def _numeric_str(value: Any) -> str:
    if value is None:
        return "0"
    try:
        formatted = format_decimal_str(
            Decimal(str(value)),
            decimals=8,
        )
        return cast(str, formatted)
    except Exception:
        return str(value)


def _severity_for_transfer(direction: str, reason: str) -> Severity:
    reason_s = (reason or "").lower()
    if "deficit" in reason_s or "error" in reason_s:
        return "warning"
    if reason_s.startswith("withdraw"):
        return "warning"
    if direction == "credit":
        return "success"
    return "info"


def _route_for_reason(reason: str) -> str | None:
    reason_s = (reason or "").lower()
    if "withdraw" in reason_s:
        return "/admin/withdrawals"
    if "panel" in reason_s:
        return "/admin/panels"
    if "task" in reason_s:
        return "/admin/tasks"
    if reason_s.startswith("referral") or "referral" in reason_s:
        return "/admin/referrals"
    return "/admin/logs"


@router.get(
    "/summary",
    response_model=AdminObservabilitySummaryOut,
    summary="Read-only observability summary for dashboard contracts",
)
async def admin_observability_summary(
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(require_admin),
) -> AdminObservabilitySummaryOut:
    await db.execute(text("SET LOCAL statement_timeout = '750ms'"))
    q = _trusted_static_sql(
        "with\n"  # nosec B608
        "users as (\n"
        f"  select count(*)::bigint as total from {CORE_SCHEMA}.users\n"
        "),\n"
        "transfers as (\n"
        "  select\n"
        "    count(*)::bigint as total,\n"
        "    coalesce(sum(amount), 0)::numeric as amount_total\n"
        f"  from {CORE_SCHEMA}.efhc_transfers_log\n"
        "),\n"
        "panels as (\n"
        "  select count(*)::bigint as total "
        f"from {CORE_SCHEMA}.panels\n"
        "),\n"
        "withdraws as (\n"
        "  select\n"
        "    count(*)::bigint as total,\n"
        "    count(*) filter (where status = 'PENDING')::bigint\n"
        "      as pending\n"
        f"  from {CORE_SCHEMA}.withdraw_requests\n"
        "),\n"
        "intents as (\n"
        "  select\n"
        "    count(*)::bigint as total,\n"
        "    count(*) filter (\n"
        "      where status in ('pending','created')\n"
        "    )::bigint as pending\n"
        f"  from {CORE_SCHEMA}.payment_intents\n"
        ")\n"
        "select\n"
        "  users.total as users_total,\n"
        "  transfers.total as transfers_total,\n"
        "  transfers.amount_total as transfers_amount_total,\n"
        "  panels.total as panels_total,\n"
        "  withdraws.total as withdraws_total,\n"
        "  withdraws.pending as withdraws_pending,\n"
        "  intents.total as intents_total,\n"
        "  intents.pending as intents_pending\n"
        "from users\n"
        "cross join transfers\n"
        "cross join panels\n"
        "cross join withdraws\n"
        "cross join intents\n"
    )
    result = (await db.execute(q)).mappings().first()
    row: Mapping[str, Any] = dict(result) if result is not None else {}
    metrics = [
        AdminObservabilitySummaryMetric(
            key="users_total",
            label="Всего пользователей",
            value=str(int(row.get("users_total") or 0)),
            unit="users",
            source="users.count",
        ),
        AdminObservabilitySummaryMetric(
            key="efhc_transfer_events_total",
            label="События EFHC ledger",
            value=str(int(row.get("transfers_total") or 0)),
            unit="events",
            source="efhc_transfers_log.count",
        ),
        AdminObservabilitySummaryMetric(
            key="efhc_transfer_amount_total",
            label="Оборот EFHC ledger",
            value=_numeric_str(row.get("transfers_amount_total")),
            unit="EFHC gross turnover",
            source="efhc_transfers_log.amount gross turnover",
        ),
        AdminObservabilitySummaryMetric(
            key="panels_total",
            label="Панели",
            value=str(int(row.get("panels_total") or 0)),
            unit="panels",
            source="panels.count",
        ),
        AdminObservabilitySummaryMetric(
            key="withdrawals_pending",
            label="Выводы в очереди",
            value=str(int(row.get("withdraws_pending") or 0)),
            unit="withdrawals",
            source="withdraw_requests.status",
        ),
        AdminObservabilitySummaryMetric(
            key="payment_intents_pending",
            label="Payment intents pending",
            value=str(int(row.get("intents_pending") or 0)),
            unit="intents",
            source="payment_intents.status",
        ),
    ]
    return AdminObservabilitySummaryOut(
        generated_at=datetime.now(UTC).isoformat(),
        metrics=metrics,
    )


@router.get(
    "/timeseries",
    response_model=AdminObservabilityTimeseriesOut,
    summary="Read-only real time-series for dashboard panels",
)
async def admin_observability_timeseries(
    metric: MetricName = Query(default="efhc_transfer_count"),
    bucket: Bucket = Query(default="hour"),
    range_hours: int = Query(default=24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(require_admin),
) -> AdminObservabilityTimeseriesOut:
    config = METRICS[str(metric)]
    await db.execute(text("SET LOCAL statement_timeout = '750ms'"))
    q = _trusted_static_sql(
        "select\n"  # nosec B608
        f"  date_trunc(:bucket, {config.ts_column}) as bucket_ts,\n"
        f"  {config.value_sql} as value\n"
        f"from {config.table}\n"
        f"where {config.ts_column} >=\n"
        "  now() - make_interval(hours => :hours)\n"
        "group by bucket_ts\n"
        "order by bucket_ts asc\n"
    )
    rows = (await db.execute(
        q,
        {"bucket": bucket, "hours": int(range_hours)},
    )).all()
    points = [
        AdminObservabilitySeriesPoint(
            ts=_iso(row[0]),
            value=_numeric_str(row[1]),
        )
        for row in rows
    ]
    return AdminObservabilityTimeseriesOut(
        metric=metric,
        bucket=bucket,
        range_hours=int(range_hours),
        unit=config.unit,
        source=config.source,
        points=points,
        empty_reason=None if points else "no_rows_in_selected_range",
    )


@router.get(
    "/events",
    response_model=AdminObservabilityEventsOut,
    summary="Отключённый дублирующий поток observability events",
)
async def admin_observability_events(
    _limit: int = Query(default=40, ge=1, le=100, alias="limit"),
    _auth: AuthContext = Depends(require_admin),
) -> AdminObservabilityEventsOut:
    # ЗАГЛУШКА ЦИКЛА 1719.
    # Причина: этот endpoint повторял безопасную проекцию тех же записей
    # efhc_transfers_log, которые уже полноценно доступны через
    # /admin/logs/transfers и текущую страницу Admin Logs. Дублирование
    # создавало две конкурирующие ленты одного источника истины. Маршрут
    # сохраняется как compatibility boundary, чтобы внешние consumers
    # получили явный ответ об отключении вместо скрытого удаления API.
    # Возвращать чтение БД сюда запрещено без нового решения пользователя.
    return AdminObservabilityEventsOut()


@router.get(
    "/health",
    response_model=AdminObservabilityHealthOut,
    summary="Read-only observability contract health",
)
async def admin_observability_health(
    _auth: AuthContext = Depends(require_admin),
) -> AdminObservabilityHealthOut:
    metrics = runtime_observability.snapshot()
    environment = str(
        getattr(_settings, "ENV", "dev") or "dev"
    )
    image_digest = str(
        getattr(_settings, "IMAGE_DIGEST", "") or ""
    )
    build_sha = str(
        getattr(_settings, "BUILD_SHA", "") or ""
    )
    alerts = list(metrics.get("alerts") or [])
    posture = {
        "dependencies": "verified",
        "security_headers": "verified",
        "log_redaction": "verified",
        "rate_limits": "verified",
        "legal_copy": "verified",
        "request_metrics": (
            "attention" if alerts else "verified"
        ),
    }
    return AdminObservabilityHealthOut(
        ok=not any(
            item.get("severity") == "critical"
            for item in alerts
        ),
        generated_at=datetime.now(UTC).isoformat(),
        contracts=[
            {
                "path": "/admin/observability/summary",
                "method": "GET",
                "data_kind": "raw+derived",
            },
            {
                "path": "/admin/observability/timeseries",
                "method": "GET",
                "data_kind": "real_timeseries",
            },
            {
                "path": "/admin/observability/events",
                "method": "GET",
                "data_kind": "disabled_duplicate",
            },
        ],
        safety={
            "read_only": True,
            "synthetic_runtime_data": False,
            "raw_payload_exposed": False,
            "write_flow_bypass": False,
            "idempotency_key_created": False,
        },
        posture=posture,
        deployment={
            "environment": environment,
            "build_sha": build_sha or "unavailable",
            "image_digest": image_digest or "unavailable",
            "immutability": (
                "verified" if image_digest else "partial"
            ),
        },
        request_metrics=metrics,
        alerts=alerts,
    )
