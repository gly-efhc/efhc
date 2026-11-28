"""Суточная консолидация ADS telemetry и AUTO REVENUE OPTIMIZER.

Job не придумывает revenue внешних сетей. Он агрегирует только фактически
сохранённые ``ad_sessions``/``ad_events`` EFHC. Provider statistics API может
быть добавлен adapter-методом позже только по подтверждённому официальному
контракту конкретной сети.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.core.config_core import get_settings
from app.core.database_core import db_session
from app.core.logging_core import get_logger
from app.lib.time import utcnow
from app.models.ads_models import (
    AdEvent,
    AdProviderDailyMetric,
    AdSession,
)
from app.services.ads.revenue_optimizer import (
    apply_revenue_recommendation,
)
from sqlalchemy import delete, func, select

logger = get_logger("efhc.scheduler.ads_revenue_importer")
settings = get_settings()


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return start, start + timedelta(days=1)


async def _aggregate_day(db: Any, day: date) -> int:
    start, end = _day_bounds(day)
    await db.execute(
        delete(AdProviderDailyMetric).where(AdProviderDailyMetric.metric_date == day)
    )

    # Попытки mediation считаем по append-only событиям provider. Это важно
    # для цепочки A → no-fill → B: запрос/no-fill A не должен исчезать из
    # суточной статистики только потому, что финальный показ выполнил B.
    event_rows = (
        await db.execute(
            select(
                AdEvent.provider.label("provider"),
                AdSession.country_code.label("country_code"),
                AdSession.app_language.label("app_language"),
                AdEvent.task_code.label("task_code"),
                func.count(AdEvent.id).filter(AdEvent.event_type == "ad_requested").label("requests"),
                func.count(AdEvent.id).filter(AdEvent.event_type == "provider_selected").label("fills"),
                func.count(AdEvent.id).filter(AdEvent.event_type == "impression").label("impressions"),
                func.count(AdEvent.id).filter(AdEvent.event_type == "completed").label("completed_views"),
                func.count(AdEvent.id).filter(AdEvent.event_type == "valued").label("valued_events"),
                func.count(AdEvent.id).filter(AdEvent.event_type == "click").label("clicks"),
                func.count(AdEvent.id).filter(AdEvent.event_type == "fallback_in").label("fallbacks_in"),
                func.count(AdEvent.id).filter(AdEvent.event_type == "fallback_out").label("fallbacks_out"),
                func.count(AdEvent.id).filter(
                    AdEvent.event_type.in_(("provider_error", "timeout", "preload_failed", "fraud_rejected"))
                ).label("errors"),
                func.count(AdEvent.id).filter(AdEvent.event_type == "no_fill").label("no_fill"),
            )
            .join(AdSession, AdSession.session_id == AdEvent.session_id)
            .where(
                AdEvent.ts >= start,
                AdEvent.ts < end,
                AdEvent.provider.is_not(None),
                AdSession.test_mode.is_(False),
            )
            .group_by(
                AdEvent.provider,
                AdSession.country_code,
                AdSession.app_language,
                AdEvent.task_code,
            )
        )
    ).all()

    # Revenue относится к фактически показавшей сети и хранится на session;
    # event telemetry не суммируем, чтобы не задвоить одну цену на нескольких
    # lifecycle-событиях.
    revenue_rows = (
        await db.execute(
            select(
                AdSession.actual_provider.label("provider"),
                AdSession.country_code.label("country_code"),
                AdSession.app_language.label("app_language"),
                AdSession.task_code.label("task_code"),
                func.coalesce(func.sum(AdSession.estimated_revenue_usd), 0).label("estimated"),
                func.coalesce(func.sum(AdSession.actual_revenue_usd), 0).label("confirmed"),
            )
            .where(
                AdSession.started_at >= start,
                AdSession.started_at < end,
                AdSession.test_mode.is_(False),
                AdSession.actual_provider.is_not(None),
            )
            .group_by(
                AdSession.actual_provider,
                AdSession.country_code,
                AdSession.app_language,
                AdSession.task_code,
            )
        )
    ).all()

    def _key(provider: Any, country: Any, language: Any, task: Any) -> tuple[str, str | None, str | None, str | None]:
        return (
            str(provider or ""),
            str(country) if country else None,
            str(language) if language else None,
            str(task) if task else None,
        )

    event_by_key = {
        _key(row.provider, row.country_code, row.app_language, row.task_code): row
        for row in event_rows
        if row.provider
    }
    revenue_by_key = {
        _key(row.provider, row.country_code, row.app_language, row.task_code): row
        for row in revenue_rows
        if row.provider
    }
    all_keys = sorted(set(event_by_key) | set(revenue_by_key), key=lambda item: tuple(x or "" for x in item))

    written = 0
    for key in all_keys:
        provider, country_code, app_language, task_code = key
        events = event_by_key.get(key)
        revenue = revenue_by_key.get(key)
        db.add(
            AdProviderDailyMetric(
                metric_date=day,
                provider=provider,
                country_code=country_code,
                app_language=app_language,
                task_code=task_code,
                requests=int(getattr(events, "requests", 0) or 0),
                fills=int(getattr(events, "fills", 0) or 0),
                impressions=int(getattr(events, "impressions", 0) or 0),
                completed_views=int(getattr(events, "completed_views", 0) or 0),
                valued_events=int(getattr(events, "valued_events", 0) or 0),
                clicks=int(getattr(events, "clicks", 0) or 0),
                fallbacks_in=int(getattr(events, "fallbacks_in", 0) or 0),
                fallbacks_out=int(getattr(events, "fallbacks_out", 0) or 0),
                errors=int(getattr(events, "errors", 0) or 0),
                no_fill=int(getattr(events, "no_fill", 0) or 0),
                estimated_revenue_usd=Decimal(getattr(revenue, "estimated", 0) or 0),
                confirmed_revenue_usd=Decimal(getattr(revenue, "confirmed", 0) or 0),
            )
        )
        written += 1
    return written


async def run_once() -> dict[str, Any]:
    """Обновить сегодня/вчера и, при включённом режиме, применить optimizer."""
    today = utcnow().date()
    async with db_session() as db:
        yesterday_rows = await _aggregate_day(db, today - timedelta(days=1))
        today_rows = await _aggregate_day(db, today)
        optimizer_result: dict[str, Any] | None = None
        if bool(getattr(settings, "ADS_AUTO_REVENUE_OPTIMIZER", False)):
            optimizer_result = await apply_revenue_recommendation(db, period="30d", force=True)
        await db.commit()
    logger.info(
        "ads_revenue_importer: yesterday=%s today=%s optimizer=%s",
        yesterday_rows,
        today_rows,
        bool(optimizer_result),
    )
    return {
        "yesterday_rows": yesterday_rows,
        "today_rows": today_rows,
        "optimizer": optimizer_result,
    }


__all__ = ["run_once"]
