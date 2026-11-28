"""Admin ADS analytics поверх server-owned ad_sessions/ad_events.

Метрики строятся из фактических EFHC событий. Провайдерный CPM никогда не
используется как единственный критерий доходности: dashboard показывает
fill/completion/fallback и revenue per request/completed view.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from app.core.decimal_utils import d8
from app.lib.time import utcnow
from app.models.ads_models import AdEvent, AdSession
from sqlalchemy import and_, case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession


def _period_bounds(
    period: str,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> tuple[datetime, datetime]:
    now = utcnow()
    key = str(period or "7d").strip().lower()
    if key == "custom":
        if date_from is None or date_to is None or date_from >= date_to:
            raise ValueError("INVALID_CUSTOM_PERIOD")
        return date_from, date_to
    delta = {
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
    }.get(key)
    if delta is None:
        raise ValueError("INVALID_PERIOD")
    return now - delta, now


def _ratio(num: int | Decimal, den: int | Decimal) -> float:
    denominator = float(den or 0)
    return 0.0 if denominator <= 0 else float(num or 0) / denominator


def _money(value: Any) -> str:
    return str(d8(value or Decimal("0")))


def _provider_row(
    values: Any,
    *,
    estimated_revenue: Decimal = Decimal("0"),
    confirmed_revenue: Decimal = Decimal("0"),
) -> dict[str, Any]:
    requests = int(values.requests or 0)
    fills = int(values.fills or 0)
    impressions = int(values.impressions or 0)
    completions = int(values.completions or 0)
    rewards = int(values.rewards or 0)
    valued = int(values.valued or 0)
    clicks = int(values.clicks or 0)
    no_fill = int(values.no_fill or 0)
    errors = int(values.errors or 0)
    fallback_out = int(values.fallback_out or 0)
    estimated = Decimal(estimated_revenue or 0)
    confirmed = Decimal(confirmed_revenue or 0)
    revenue = confirmed if confirmed > 0 else estimated
    return {
        "provider": values.provider or "unknown",
        "requests": requests,
        "fills": fills,
        "fill_rate": _ratio(fills, requests),
        "shows": impressions,
        "completion_rate": _ratio(completions, impressions),
        "valued_rate": _ratio(valued, completions),
        "completions": completions,
        "rewards": rewards,
        "estimated_revenue_usd": _money(estimated),
        "confirmed_revenue_usd": _money(confirmed),
        "revenue_per_request_usd": _money(revenue / requests if requests else 0),
        "revenue_per_completed_usd": _money(revenue / completions if completions else 0),
        "ecpm_usd": _money((revenue / impressions * 1000) if impressions else 0),
        "erpm_usd": _money((revenue / requests * 1000) if requests else 0),
        "valued_events": valued,
        "clicks": clicks,
        "errors": errors,
        "no_fill": no_fill,
        "fallback_in": int(values.fallback_in or 0),
        "fallback_out": fallback_out,
    }


async def ads_dashboard(
    db: AsyncSession,
    *,
    period: str = "7d",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[str, Any]:
    start, end = _period_bounds(period, date_from=date_from, date_to=date_to)
    scope = and_(AdSession.started_at >= start, AdSession.started_at < end, AdSession.test_mode.is_(False))

    overall = (
        await db.execute(
            select(
                func.count(AdSession.session_id).label("requests"),
                func.count(AdSession.session_id).filter(AdSession.shown_at.is_not(None)).label("impressions"),
                func.count(AdSession.session_id).filter(AdSession.completed_at.is_not(None)).label("completed"),
                func.count(distinct(AdSession.global_id)).filter(AdSession.rewarded_at.is_not(None)).label("rewarded_users"),
                func.count(AdSession.session_id).filter(AdSession.status == "no_fill").label("no_fill"),
                func.count(AdSession.session_id).filter(AdSession.status.in_(("failed", "fraud_rejected", "expired"))).label("errors"),
                func.coalesce(func.sum(AdSession.fallback_count), 0).label("fallback"),
                func.coalesce(func.sum(case((AdSession.rewarded_at.is_not(None), AdSession.reward_snapshot_efhcb), else_=0)), 0).label("distributed"),
                func.coalesce(func.sum(AdSession.estimated_revenue_usd), 0).label("estimated"),
                func.coalesce(func.sum(AdSession.actual_revenue_usd), 0).label("confirmed"),
            ).where(scope)
        )
    ).one()
    requests = int(overall.requests or 0)
    completed = int(overall.completed or 0)
    revenue = Decimal(overall.confirmed or 0) if Decimal(overall.confirmed or 0) > 0 else Decimal(overall.estimated or 0)

    # Provider mediation analytics считается по append-only ad_events, а не
    # только по финальному ``actual_provider`` session. Иначе при A → no-fill
    # → B successful запрос/ошибка A исчезают из статистики и Revenue
    # Optimizer получает ложную картину доходности. Revenue при этом берём
    # отдельно из финальной session, где он принадлежит фактически показавшей
    # сети.
    event_scope = and_(
        AdEvent.ts >= start,
        AdEvent.ts < end,
        AdEvent.provider.is_not(None),
        AdSession.test_mode.is_(False),
    )
    grouped = (
        await db.execute(
            select(
                AdEvent.provider.label("provider"),
                func.count(AdEvent.id).filter(AdEvent.event_type == "ad_requested").label("requests"),
                func.count(AdEvent.id).filter(AdEvent.event_type == "provider_selected").label("fills"),
                func.count(AdEvent.id).filter(AdEvent.event_type == "impression").label("impressions"),
                func.count(AdEvent.id).filter(AdEvent.event_type == "completed").label("completions"),
                func.count(AdEvent.id).filter(AdEvent.event_type == "reward_credited").label("rewards"),
                func.count(AdEvent.id).filter(AdEvent.event_type == "valued").label("valued"),
                func.count(AdEvent.id).filter(AdEvent.event_type == "click").label("clicks"),
                func.count(AdEvent.id).filter(AdEvent.event_type == "no_fill").label("no_fill"),
                func.count(AdEvent.id).filter(
                    AdEvent.event_type.in_(("provider_error", "timeout", "preload_failed", "fraud_rejected"))
                ).label("errors"),
                func.count(AdEvent.id).filter(AdEvent.event_type == "fallback_in").label("fallback_in"),
                func.count(AdEvent.id).filter(AdEvent.event_type == "fallback_out").label("fallback_out"),
            )
            .join(AdSession, AdSession.session_id == AdEvent.session_id)
            .where(event_scope)
            .group_by(AdEvent.provider)
        )
    ).all()
    revenue_rows = (
        await db.execute(
            select(
                AdSession.actual_provider.label("provider"),
                func.coalesce(func.sum(AdSession.estimated_revenue_usd), 0).label("estimated"),
                func.coalesce(func.sum(AdSession.actual_revenue_usd), 0).label("confirmed"),
            )
            .where(scope, AdSession.actual_provider.is_not(None))
            .group_by(AdSession.actual_provider)
        )
    ).all()
    revenue_by_provider = {
        str(row.provider): (Decimal(row.estimated or 0), Decimal(row.confirmed or 0))
        for row in revenue_rows
        if row.provider
    }
    by_provider: list[dict[str, Any]] = []
    for row in grouped:
        estimated, confirmed = revenue_by_provider.get(
            str(row.provider), (Decimal("0"), Decimal("0"))
        )
        by_provider.append(
            _provider_row(
                row,
                estimated_revenue=estimated,
                confirmed_revenue=confirmed,
            )
        )
    by_provider.sort(
        key=lambda row: (
            Decimal(row["confirmed_revenue_usd"]),
            Decimal(row["estimated_revenue_usd"]),
        ),
        reverse=True,
    )

    async def dimension_rows(column: Any, name: str) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(
                    column.label(name),
                    func.count(AdSession.session_id).label("requests"),
                    func.count(AdSession.session_id).filter(AdSession.rewarded_at.is_not(None)).label("successful_views"),
                    func.coalesce(func.sum(AdSession.estimated_revenue_usd), 0).label("estimated"),
                    func.coalesce(func.sum(AdSession.actual_revenue_usd), 0).label("confirmed"),
                ).where(scope).group_by(column)
            )
        ).all()
        result: list[dict[str, Any]] = []
        for row in rows:
            if getattr(row, name) in (None, ""):
                continue
            result.append({
                name: getattr(row, name),
                "requests": int(row.requests or 0),
                "successful_views": int(row.successful_views or 0),
                "estimated_revenue_usd": _money(row.estimated),
                "confirmed_revenue_usd": _money(row.confirmed),
            })
        return result

    by_geo = await dimension_rows(AdSession.country_code, "country")
    by_language = await dimension_rows(AdSession.app_language, "language")

    task_rows = (
        await db.execute(
            select(
                AdSession.task_code,
                AdSession.primary_provider,
                AdSession.actual_provider,
                func.count(AdSession.session_id).label("completions"),
                func.coalesce(func.sum(case((AdSession.rewarded_at.is_not(None), AdSession.reward_snapshot_efhcb), else_=0)), 0).label("reward"),
                func.coalesce(func.sum(AdSession.estimated_revenue_usd), 0).label("estimated"),
                func.coalesce(func.sum(AdSession.actual_revenue_usd), 0).label("confirmed"),
                func.coalesce(func.sum(AdSession.fallback_count), 0).label("fallback"),
            ).where(scope, AdSession.completed_at.is_not(None)).group_by(
                AdSession.task_code, AdSession.primary_provider, AdSession.actual_provider
            )
        )
    ).all()
    by_task = [{
        "task": row.task_code,
        "primary_provider": row.primary_provider,
        "actual_provider": row.actual_provider,
        "completions": int(row.completions or 0),
        "reward_efhcb": _money(row.reward),
        "estimated_revenue_usd": _money(row.estimated),
        "confirmed_revenue_usd": _money(row.confirmed),
        "fallback_count": int(row.fallback or 0),
    } for row in task_rows]

    day_bucket = func.date_trunc("day", AdSession.started_at)
    timeline_rows = (
        await db.execute(
            select(
                day_bucket.label("bucket"),
                func.count(AdSession.session_id).label("requests"),
                func.count(AdSession.session_id).filter(AdSession.rewarded_at.is_not(None)).label("rewarded_views"),
                func.count(AdSession.session_id).filter(AdSession.status == "no_fill").label("no_fill"),
                func.count(AdSession.session_id).filter(AdSession.status.in_(("failed", "fraud_rejected", "expired"))).label("errors"),
                func.coalesce(func.sum(AdSession.estimated_revenue_usd), 0).label("estimated"),
                func.coalesce(func.sum(AdSession.actual_revenue_usd), 0).label("confirmed"),
            ).where(scope).group_by(day_bucket).order_by(day_bucket)
        )
    ).all()
    timeline = [{
        "date": row.bucket.date().isoformat() if row.bucket else None,
        "requests": int(row.requests or 0),
        "rewarded_views": int(row.rewarded_views or 0),
        "no_fill": int(row.no_fill or 0),
        "errors": int(row.errors or 0),
        "estimated_revenue_usd": _money(row.estimated),
        "confirmed_revenue_usd": _money(row.confirmed),
    } for row in timeline_rows]

    # Лучший provider по GEO определяется по наблюдаемому подтверждённому или оценочному доходу.
    geo_provider_rows = (
        await db.execute(
            select(
                AdSession.country_code,
                AdSession.actual_provider,
                func.coalesce(func.sum(AdSession.actual_revenue_usd), 0).label("confirmed"),
                func.coalesce(func.sum(AdSession.estimated_revenue_usd), 0).label("estimated"),
            ).where(scope, AdSession.country_code.is_not(None), AdSession.actual_provider.is_not(None))
            .group_by(AdSession.country_code, AdSession.actual_provider)
        )
    ).all()
    best_geo: dict[str, tuple[str, Decimal]] = {}
    for row in geo_provider_rows:
        value = Decimal(row.confirmed or 0) if Decimal(row.confirmed or 0) > 0 else Decimal(row.estimated or 0)
        current = best_geo.get(str(row.country_code))
        if current is None or value > current[1]:
            best_geo[str(row.country_code)] = (str(row.actual_provider), value)
    for geo_item in by_geo:
        best = best_geo.get(str(geo_item["country"]))
        geo_item["best_provider"] = best[0] if best else None

    return {
        "period": period,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "overall": {
            "ad_requests": requests,
            "impressions": int(overall.impressions or 0),
            "completed_rewarded_views": completed,
            "rewarded_users": int(overall.rewarded_users or 0),
            "provider_no_fill": int(overall.no_fill or 0),
            "errors": int(overall.errors or 0),
            "fallback": int(overall.fallback or 0),
            "efhcb_distributed": _money(overall.distributed),
            "estimated_revenue_usd": _money(overall.estimated),
            "confirmed_revenue_usd": _money(overall.confirmed),
            "revenue_per_1000_requests_usd": _money((revenue / requests * 1000) if requests else 0),
            "revenue_per_completed_ad_usd": _money((revenue / completed) if completed else 0),
        },
        "providers": by_provider,
        "geo": by_geo,
        "languages": by_language,
        "tasks": by_task,
        "timeline": timeline,
        "fallback_distribution": [
            {
                "provider": row["provider"],
                "fallback_in": row["fallback_in"],
                "fallback_out": row["fallback_out"],
            }
            for row in by_provider
        ],
    }


__all__ = ["ads_dashboard"]
