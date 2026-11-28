"""HTTP boundary единого рекламного AdManager EFHC.

Новые страницы используют только ``/ads/session*``. Исторические
``/ads/slot`` и ``/ads/callback/{provider}`` сохранены как compatibility
surface, но больше не являются production reward architecture.
"""

from __future__ import annotations

import hmac
from datetime import timedelta
from decimal import Decimal
from typing import Any, Never, cast

from app.core.config_core import get_settings
from app.core.decimal_utils import d8
from app.deps import get_db
from app.identity.nonfinancial_owner import NonFinancialReadOwner
from app.identity.nonfinancial_read_dependency import (
    get_nonfinancial_read_owner,
)
from app.identity.telegram_auth_session import (
    resolve_telegram_subject_global_id,
)
from app.identity.types import format_global_id, global_id_from_database
from app.integrations.ads.common import correlation_session_id
from app.integrations.ads_providers import (
    get_verified_event,
    issue_builtin_timer_token,
)
from app.lib.time import utcnow
from app.models.ads_models import AdEvent, AdSession
from app.models.tasks_models import Task
from app.services.ads.ad_manager import (
    AdContext,
    AdManagerError,
    client_complete,
    create_session,
    fallback_session,
    get_session,
    mark_shown,
    provider_postback,
    record_client_telemetry,
)
from app.services.ads.config_service import load_provider_config
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

settings = get_settings()
router = APIRouter(prefix="/ads", tags=["ads"])

ACTIVE_LANGUAGES = frozenset({"en", "ru", "uk", "de", "fr", "es", "it", "tr", "pl", "da", "hi", "id", "sw", "pt", "ko", "ja"})


async def _require_provider_postback_secret(
    db: AsyncSession,
    *,
    provider: str,
    supplied: str,
) -> None:
    """Проверить provider postback secret отдельно от session correlation."""

    cfg = await load_provider_config(db, provider)
    expected = str(cfg.secret.get("postback_secret") or "").strip()
    candidate = str(supplied or "").strip()
    if (
        not expected
        or not candidate
        or not hmac.compare_digest(candidate, expected)
    ):
        raise HTTPException(status_code=403, detail="VERIFICATION_FAILED")


class AdSessionCreateIn(BaseModel):
    task_code: str = Field(min_length=1, max_length=64)


class AdFallbackIn(BaseModel):
    reason: str = Field(default="PROVIDER_ERROR", max_length=64)


class AdClientEventIn(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class AdTelemetryIn(BaseModel):
    event_type: str = Field(min_length=1, max_length=48)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AdSessionOut(BaseModel):
    session_id: str
    task_code: str
    status: str
    primary_provider: str | None = None
    actual_provider: str | None = None
    provider: dict[str, Any] | None = None
    reward_efhcb: str
    expires_at: str
    failure_code: str | None = None
    fallback_count: int
    verification_level: str | None = None
    estimated_revenue_usd: str | None = None
    actual_revenue_usd: str | None = None
    rewarded: bool
    test_mode: bool


# Compatibility schema старого /ads/slot.
class AdSlotOut(BaseModel):
    provider: str
    task_code: str
    global_id: str
    bonus_efhc: str
    token: str | None = None
    expires_at: str | None = None
    min_view_sec: int | None = None
    placement_id: str | None = None


class AdCallbackResultOut(BaseModel):
    ok: bool
    provider: str
    task_code: str
    provider_ref: str
    bonus_efhc: str
    replayed: bool = False


def _raise_manager(exc: AdManagerError) -> Never:
    raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc


def _owner_display(owner: NonFinancialReadOwner) -> str:
    return str(format_global_id(global_id_from_database(owner.global_id)))


async def _stored_language(db: AsyncSession, owner: NonFinancialReadOwner) -> str | None:
    row = (
        await db.execute(
            text("SELECT meta FROM efhc_core.users WHERE global_id=:gid LIMIT 1"),
            {"gid": owner.global_id},
        )
    ).scalar_one_or_none()
    if not isinstance(row, dict):
        return None
    for key in ("app_language", "ui_lang", "preferred_language", "language", "lang", "telegram_language_code", "language_code"):
        value = str(row.get(key) or "").strip()
        if value in ACTIVE_LANGUAGES:
            return value
        base = value.split("-", 1)[0].lower()
        if base in ACTIVE_LANGUAGES:
            return base
    return None


async def _ad_context(
    request: Request,
    db: AsyncSession,
    owner: NonFinancialReadOwner,
    *,
    test_mode: bool = False,
) -> AdContext:
    header_lang = str(request.headers.get("X-App-Language") or "").strip()
    language = header_lang if header_lang in ACTIVE_LANGUAGES else None
    if language is None:
        language = await _stored_language(db, owner)
    language = language or "en"

    country: str | None = None
    trusted_country_header = str(getattr(settings, "ADS_TRUSTED_COUNTRY_HEADER", "") or "").strip()
    if trusted_country_header:
        raw_country = str(request.headers.get(trusted_country_header) or "").strip().upper()
        if len(raw_country) == 2 and raw_country.isalpha():
            country = raw_country

    ip_address = request.client.host if request.client else None
    trusted_ip_header = str(getattr(settings, "ADS_TRUSTED_CLIENT_IP_HEADER", "") or "").strip()
    if trusted_ip_header:
        forwarded = str(request.headers.get(trusted_ip_header) or "").split(",", 1)[0].strip()
        if forwarded:
            ip_address = forwarded

    return AdContext(
        app_language=language,
        country_code=country,
        platform=str(request.headers.get("X-EFHC-Platform") or "telegram-miniapp")[:32],
        user_agent=str(request.headers.get("user-agent") or "")[:1024] or None,
        ip_address=ip_address,
        provider_tg_id=owner.provider_tg_id,
        telegram_premium=None,
        test_mode=test_mode,
    )


@router.post("/session", response_model=AdSessionOut)
async def ads_session_create(
    body: AdSessionCreateIn,
    request: Request,
    owner: NonFinancialReadOwner = Depends(get_nonfinancial_read_owner),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Создать rewarded ad_session и вернуть только runtime public config."""

    try:
        context = await _ad_context(request, db, owner)
        view = await create_session(
            db,
            global_id=_owner_display(owner),
            task_code=body.task_code,
            context=context,
        )
        return cast(dict[str, Any], view.as_dict())
    except AdManagerError as exc:
        _raise_manager(exc)


@router.post("/session/{session_id}/fallback", response_model=AdSessionOut)
async def ads_session_fallback(
    session_id: str,
    body: AdFallbackIn,
    request: Request,
    owner: NonFinancialReadOwner = Depends(get_nonfinancial_read_owner),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Автоматически продолжить ту же сессию следующим provider."""

    try:
        context = await _ad_context(request, db, owner)
        view = await fallback_session(
            db,
            session_id=session_id,
            global_id=_owner_display(owner),
            context=context,
            reason=body.reason,
        )
        return cast(dict[str, Any], view.as_dict())
    except AdManagerError as exc:
        _raise_manager(exc)


@router.post("/session/{session_id}/shown", response_model=AdSessionOut)
async def ads_session_shown(
    session_id: str,
    owner: NonFinancialReadOwner = Depends(get_nonfinancial_read_owner),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return cast(
            dict[str, Any],
            (await mark_shown(db, session_id=session_id, global_id=_owner_display(owner))).as_dict(),
        )
    except AdManagerError as exc:
        _raise_manager(exc)




@router.post("/session/{session_id}/event", response_model=AdSessionOut)
async def ads_session_client_event(
    session_id: str,
    body: AdTelemetryIn,
    owner: NonFinancialReadOwner = Depends(get_nonfinancial_read_owner),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Безопасная SDK telemetry. Никогда не является reward proof."""

    try:
        return cast(
            dict[str, Any],
            (
                await record_client_telemetry(
                    db,
                    session_id=session_id,
                    global_id=_owner_display(owner),
                    event_type=body.event_type,
                    metadata=body.metadata,
                )
            ).as_dict(),
        )
    except AdManagerError as exc:
        _raise_manager(exc)


@router.post("/session/{session_id}/client-complete", response_model=AdSessionOut)
async def ads_session_client_complete(
    session_id: str,
    body: AdClientEventIn,
    owner: NonFinancialReadOwner = Depends(get_nonfinancial_read_owner),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """SDK completion; trust level provider-specific, не универсальный reward proof."""

    try:
        return cast(
            dict[str, Any],
            (
                await client_complete(
                    db,
                    session_id=session_id,
                    global_id=_owner_display(owner),
                    payload=body.payload,
                )
            ).as_dict(),
        )
    except AdManagerError as exc:
        _raise_manager(exc)


@router.get("/session/{session_id}", response_model=AdSessionOut)
async def ads_session_state(
    session_id: str,
    owner: NonFinancialReadOwner = Depends(get_nonfinancial_read_owner),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return cast(
            dict[str, Any],
            (await get_session(db, session_id=session_id, global_id=_owner_display(owner))).as_dict(),
        )
    except AdManagerError as exc:
        _raise_manager(exc)


@router.get("/postback/monetag")
async def monetag_postback(
    ymid: str,
    efhc_token: str = Query(default=""),
    event_type: str = Query(default="impression"),
    reward_event_type: str = Query(default=""),
    estimated_price: str | None = None,
    zone_id: str | None = None,
    sub_zone_id: str | None = None,
    request_var: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Server postback Monetag; ``ymid`` содержит подписанную корреляцию EFHC session."""

    await _require_provider_postback_secret(
        db,
        provider="monetag",
        supplied=efhc_token,
    )
    session_id = correlation_session_id(ymid)
    if not session_id:
        raise HTTPException(status_code=403, detail="VERIFICATION_FAILED")
    payload = {
        "ymid": ymid,
        "event_type": event_type,
        "reward_event_type": reward_event_type,
        "estimated_price": estimated_price,
        "zone_id": zone_id,
        "sub_zone_id": sub_zone_id,
        "request_var": request_var,
    }
    try:
        view = await provider_postback(db, provider="monetag", session_id=session_id, payload=payload)
        return {"ok": True, "status": view.status}
    except AdManagerError as exc:
        _raise_manager(exc)


@router.get("/postback/admaven")
async def admaven_postback(
    click_id: str = Query(alias="CLICK_ID"),
    efhc_token: str = Query(default=""),
    event_id: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """AdMaven server postback с signed CLICK_ID correlation."""

    await _require_provider_postback_secret(
        db,
        provider="admaven",
        supplied=efhc_token,
    )
    session_id = correlation_session_id(click_id)
    if not session_id:
        raise HTTPException(status_code=403, detail="VERIFICATION_FAILED")
    try:
        view = await provider_postback(
            db,
            provider="admaven",
            session_id=session_id,
            payload={"CLICK_ID": click_id, "event_id": event_id},
        )
        return {"ok": True, "status": view.status}
    except AdManagerError as exc:
        _raise_manager(exc)


@router.get("/postback/adsgram")
async def adsgram_reward_url_signal(
    provider_tg_id: int = Query(alias="userId"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Дополнительный AdsGram Reward URL signal; сам по себе EFHCb не выдаёт."""

    global_id = await resolve_telegram_subject_global_id(db, provider_tg_id)
    if global_id is None:
        return {"ok": True, "matched": False}
    cutoff = utcnow() - timedelta(minutes=30)
    session = (
        await db.execute(
            select(AdSession)
            .where(
                AdSession.global_id == global_id.value,
                AdSession.actual_provider == "adsgram",
                AdSession.started_at >= cutoff,
            )
            .order_by(AdSession.started_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if session is None:
        return {"ok": True, "matched": False}
    provider_event_id = f"adsgram-reward-url:{session.session_id}"
    existing = (
        await db.execute(
            select(AdEvent.id).where(
                AdEvent.provider == "adsgram",
                AdEvent.provider_event_id == provider_event_id,
                AdEvent.event_type == "postback_received",
            ).limit(1)
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(
            AdEvent(
                session_id=session.session_id,
                provider="adsgram",
                task_code=session.task_code,
                event_type="postback_received",
                provider_event_id=provider_event_id,
                metadata_json={"source": "reward_url", "reward_authority": False},
            )
        )
        await db.commit()
    return {"ok": True, "matched": True}


# ---------------------------------------------------------------------------
# Compatibility surfaces. Новый frontend на них не строится.
# ---------------------------------------------------------------------------


@router.get("/slot", response_model=AdSlotOut)
async def get_ad_slot_compat(
    task_code: str,
    provider: str | None = None,
    owner: NonFinancialReadOwner = Depends(get_nonfinancial_read_owner),
    db: AsyncSession = Depends(get_db),
) -> AdSlotOut:
    """Compatibility-only slot. builtin_timer доступен только ADS_TEST_MODE."""

    task = (
        await db.execute(select(Task).where(Task.code == task_code).limit(1))
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Задание не найдено")
    if not task.active or task.type != "watch_ad":
        raise HTTPException(status_code=409, detail="NOT_SUPPORTED")
    selected = str(provider or "adsgram").strip().lower()
    bonus = d8(task.bonus_efhc or Decimal("0"))

    if selected == "builtin_timer":
        if not bool(settings.ADS_TEST_MODE) or not bool(settings.ADS_BUILTIN_TIMER_ENABLED):
            raise HTTPException(status_code=410, detail="NOT_SUPPORTED")
        if owner.provider_tg_id is None:
            raise HTTPException(status_code=409, detail="telegram_provider_required")
        token = issue_builtin_timer_token(
            tg_id=owner.provider_tg_id,
            task_code=task_code,
            bonus_efhc=bonus,
            ttl_sec=int(settings.ADS_BUILTIN_TOKEN_TTL_SEC),
        )
        return AdSlotOut(
            provider="builtin_timer",
            task_code=task_code,
            global_id=_owner_display(owner),
            bonus_efhc=str(bonus),
            token=token,
            expires_at=(utcnow() + timedelta(seconds=int(settings.ADS_BUILTIN_TOKEN_TTL_SEC))).isoformat(),
            min_view_sec=int(settings.ADS_BUILTIN_MIN_VIEW_SEC),
        )

    if selected != "adsgram":
        raise HTTPException(status_code=410, detail="USE_AD_MANAGER_SESSION")
    config = await load_provider_config(db, "adsgram")
    if not config.enabled or not config.is_configured():
        raise HTTPException(status_code=409, detail="NOT_CONFIGURED")
    return AdSlotOut(
        provider="adsgram",
        task_code=task_code,
        global_id=_owner_display(owner),
        bonus_efhc=str(bonus),
        placement_id=str(config.public.get("reward_block_id") or "") or None,
    )


@router.post("/callback/{provider}", response_model=AdCallbackResultOut)
async def ads_callback_compat(
    provider: str,
    body: dict[str, Any],
) -> AdCallbackResultOut:
    """Compatibility wrapper: legacy callback никогда не выдаёт production EFHCb."""

    code = str(provider or "").strip().lower()
    if code != "builtin_timer" or not bool(settings.ADS_TEST_MODE):
        raise HTTPException(status_code=410, detail="USE_AD_MANAGER_SESSION")
    try:
        evt = await get_verified_event(
            "builtin_timer",
            payload=body or {},
            headers={},
            client_ip=None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return AdCallbackResultOut(
        ok=True,
        provider="builtin_timer",
        task_code=str(evt.task_code),
        provider_ref=str(evt.provider_ref),
        bonus_efhc="0.00000000",
        replayed=False,
    )
