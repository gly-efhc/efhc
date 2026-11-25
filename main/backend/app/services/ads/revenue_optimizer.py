"""AdRevenueOptimizer: рекомендации только по фактической telemetry EFHC."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.core.config_core import get_settings
from app.models.ads_models import AdProviderConfig
from app.services.ads.analytics_service import ads_dashboard
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

settings = get_settings()


async def revenue_recommendation(
    db: AsyncSession,
    *,
    period: str = "30d",
    min_requests: int = 20,
) -> dict[str, Any]:
    dashboard = await ads_dashboard(db, period=period)
    rows: list[dict[str, Any]] = []
    for provider in dashboard["providers"]:
        requests = int(provider["requests"] or 0)
        if requests < max(1, int(min_requests)):
            rows.append({**provider, "eligible_for_ranking": False, "score": None})
            continue
        confirmed = Decimal(provider["confirmed_revenue_usd"])
        estimated = Decimal(provider["estimated_revenue_usd"])
        observed_revenue = confirmed if confirmed > 0 else estimated
        # Главный показатель = доход на фактический request. Completion/fill
        # уже входят в него естественным образом и дополнительно показываются.
        score = observed_revenue / Decimal(requests)
        rows.append({**provider, "eligible_for_ranking": True, "score": str(score)})
    ranked = sorted(
        [row for row in rows if row["eligible_for_ranking"]],
        key=lambda row: Decimal(str(row["score"])),
        reverse=True,
    )
    insufficient = [row for row in rows if not row["eligible_for_ranking"]]
    return {
        "period": period,
        "metric": "observed_revenue_per_request",
        "min_requests": max(1, int(min_requests)),
        "recommended_order": [str(row["provider"]) for row in ranked],
        "ranked": ranked,
        "insufficient_data": insufficient,
        "auto_apply_enabled": bool(getattr(settings, "ADS_AUTO_REVENUE_OPTIMIZER", False)),
        "note": "Порядок основан на фактической telemetry EFHC, а не на постоянном рейтинге рекламных сетей.",
    }


async def apply_revenue_recommendation(
    db: AsyncSession,
    *,
    period: str = "30d",
    min_requests: int = 20,
    force: bool = False,
) -> dict[str, Any]:
    if not force and not bool(getattr(settings, "ADS_AUTO_REVENUE_OPTIMIZER", False)):
        raise ValueError("AUTO_OPTIMIZER_DISABLED")
    recommendation = await revenue_recommendation(db, period=period, min_requests=min_requests)
    order = list(recommendation["recommended_order"])
    if not order:
        raise ValueError("INSUFFICIENT_REVENUE_DATA")
    configs = (
        await db.execute(select(AdProviderConfig).where(AdProviderConfig.code.in_(order)))
    ).scalars().all()
    by_code = {row.code: row for row in configs}
    for priority, code in enumerate(order):
        row = by_code.get(code)
        if row is not None:
            row.priority = priority
    await db.commit()
    return recommendation


__all__ = ["apply_revenue_recommendation", "revenue_recommendation"]
