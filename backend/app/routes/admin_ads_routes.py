"""Admin API центра управления рекламной инфраструктурой EFHC."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Never, cast

from app.deps import (
    AuthContext,
    get_db,
    require_admin,
    require_admin_write,
)
from app.identity.types import format_global_id, global_id_from_database
from app.integrations.ads.base import AdContext
from app.services.admin.admin_ads_service import (
    delete_secret,
    get_provider,
    list_providers,
    replace_secret,
    reset_provider_errors,
    save_provider,
    test_provider,
)
from app.services.ads.analytics_service import ads_dashboard
from app.services.ads.revenue_optimizer import revenue_recommendation
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/admin/ads", tags=["admin:ads"])


class ProviderSaveIn(BaseModel):
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=0)
    miniapp_enabled: bool | None = None
    bot_enabled: bool | None = None
    rewarded_enabled: bool | None = None
    public_config: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
    countries_allow: list[str] | None = None
    countries_block: list[str] | None = None
    languages_allow: list[str] | None = None
    languages_block: list[str] | None = None
    moderation_status: str | None = Field(default=None, max_length=32)


class SecretReplaceIn(BaseModel):
    field: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=8192)


class SecretDeleteIn(BaseModel):
    field: str = Field(min_length=1, max_length=64)


class ProviderTestIn(BaseModel):
    mode: str = Field(default="configuration", pattern="^(configuration|sdk|request)$")


def _error(exc: ValueError) -> Never:
    raise HTTPException(status_code=400, detail=str(exc)) from exc


def _admin_display(auth: AuthContext) -> str:
    return str(format_global_id(global_id_from_database(auth.global_id)))


def _test_context(request: Request) -> AdContext:
    return AdContext(
        app_language="en",
        country_code=None,
        platform="admin-test",
        user_agent=str(request.headers.get("user-agent") or "")[:1024] or None,
        ip_address=request.client.host if request.client else None,
        provider_tg_id=None,
        telegram_premium=None,
        test_mode=True,
    )


class RevenueOptimizerApplyIn(BaseModel):
    period: str = Field(default="30d", pattern="^(24h|7d|30d)$")
    min_requests: int = Field(default=20, ge=1, le=1_000_000)


@router.get("/dashboard")
async def admin_ads_dashboard(
    period: str = "7d",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    _auth: AuthContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Фактическая revenue/fill/completion telemetry рекламного контура."""

    try:
        return cast(
            dict[str, Any],
            await ads_dashboard(
                db,
                period=period,
                date_from=date_from,
                date_to=date_to,
            ),
        )
    except ValueError as exc:
        _error(exc)


@router.get("/revenue-optimizer")
async def admin_ads_revenue_optimizer(
    period: str = "30d",
    min_requests: int = 20,
    _auth: AuthContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return cast(
            dict[str, Any],
            await revenue_recommendation(
                db, period=period, min_requests=min_requests
            ),
        )
    except ValueError as exc:
        _error(exc)


@router.post("/revenue-optimizer/apply")
async def admin_ads_apply_revenue_optimizer(
    body: RevenueOptimizerApplyIn,
    auth: AuthContext = Depends(require_admin_write),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = cast(
            dict[str, Any],
            await revenue_recommendation(
                db, period=body.period, min_requests=body.min_requests
            ),
        )
        order = list(result.get("recommended_order") or [])
        if not order:
            raise ValueError("INSUFFICIENT_REVENUE_DATA")
        # Admin-triggered priority changes идут через canonical Admin service,
        # поэтому каждое изменение имеет audit row без секретных значений.
        for priority, code in enumerate(order):
            await save_provider(
                db,
                code=str(code),
                admin_global_id=auth.global_id,
                priority=priority,
            )
        result["applied_by"] = _admin_display(auth)
        return result
    except ValueError as exc:
        _error(exc)


@router.get("/providers")
async def admin_ads_providers(
    _auth: AuthContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Provider cards с masked secrets и runtime readiness."""

    try:
        return cast(list[dict[str, Any]], await list_providers(db))
    except ValueError as exc:
        _error(exc)


@router.get("/providers/{code}")
async def admin_ads_provider(
    code: str,
    _auth: AuthContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return cast(dict[str, Any], await get_provider(db, code))
    except (ValueError, KeyError) as exc:
        _error(ValueError(str(exc)))


@router.put("/providers/{code}")
async def admin_ads_save_provider(
    code: str,
    body: ProviderSaveIn,
    auth: AuthContext = Depends(require_admin_write),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return cast(
            dict[str, Any],
            await save_provider(
                db,
                code=code,
                admin_global_id=auth.global_id,
                **body.model_dump(exclude_none=True),
            ),
        )
    except (ValueError, KeyError) as exc:
        _error(ValueError(str(exc)))


@router.post("/providers/{code}/secrets/replace")
async def admin_ads_replace_secret(
    code: str,
    body: SecretReplaceIn,
    auth: AuthContext = Depends(require_admin_write),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return cast(
            dict[str, Any],
            await replace_secret(
                db,
                code=code,
                field_name=body.field,
                value=body.value,
                admin_global_id=auth.global_id,
            ),
        )
    except (ValueError, KeyError) as exc:
        _error(ValueError(str(exc)))


@router.post("/providers/{code}/secrets/delete")
async def admin_ads_delete_secret(
    code: str,
    body: SecretDeleteIn,
    auth: AuthContext = Depends(require_admin_write),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return cast(
            dict[str, Any],
            await delete_secret(
                db,
                code=code,
                field_name=body.field,
                admin_global_id=auth.global_id,
            ),
        )
    except (ValueError, KeyError) as exc:
        _error(ValueError(str(exc)))


@router.post("/providers/{code}/test")
async def admin_ads_test_provider(
    code: str,
    body: ProviderTestIn,
    request: Request,
    auth: AuthContext = Depends(require_admin_write),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = cast(
            dict[str, Any],
            await test_provider(
                db,
                code=code,
                admin_global_id=auth.global_id,
                context=_test_context(request),
                mode=body.mode,
            ),
        )
        result["admin_global_id"] = _admin_display(auth)
        return result
    except (ValueError, KeyError) as exc:
        _error(ValueError(str(exc)))


@router.post("/providers/{code}/reset-errors")
async def admin_ads_reset_errors(
    code: str,
    auth: AuthContext = Depends(require_admin_write),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return cast(
            dict[str, Any],
            await reset_provider_errors(
                db,
                code=code,
                admin_global_id=auth.global_id,
            ),
        )
    except (ValueError, KeyError) as exc:
        _error(ValueError(str(exc)))
