"""HTTP boundary единого рекламного AdManager EFHC.

Новые страницы используют только ``/ads/session*``. Исторические
``/ads/slot`` и ``/ads/callback/{provider}`` сохранены как compatibility
surface, но больше не являются production reward architecture.
"""

from __future__ import annotations

import hmac
from typing import Any, Never, cast

from app.core.config_core import get_settings
from app.deps import get_db
from app.identity.nonfinancial_owner import NonFinancialReadOwner
from app.identity.nonfinancial_read_dependency import (
    get_nonfinancial_read_owner,
)
from app.identity.types import format_global_id, global_id_from_database
from app.integrations.ads.common import correlation_session_id
from app.integrations.ads_providers import (
    get_verified_event,
)
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
from app.schemas.ads_schemas import (
    AdSessionCreateIn,
    AdFallbackIn,
    AdClientEventIn,
    AdTelemetryIn,
    AdSessionOut,
    AdSlotOut,
    AdCallbackResultOut,
)
from app.services.ads.config_service import load_provider_config
from app.services.ads.http_use_cases import (
    ACTIVE_LANGUAGES,
    AdSlotError,
    get_compat_slot,
    record_adsgram_reward_url_signal,
    stored_language,
)
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

settings = get_settings()
router = APIRouter(prefix="/ads", tags=["ads"])



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


def _raise_manager(exc: AdManagerError) -> Never:
    raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc


def _owner_display(owner: NonFinancialReadOwner) -> str:
    return str(format_global_id(global_id_from_database(owner.global_id)))


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
        language = await stored_language(db, global_id=owner.global_id)
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

    return await record_adsgram_reward_url_signal(db, provider_tg_id=provider_tg_id)


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

    try:
        return await get_compat_slot(db, task_code=task_code, provider=provider, global_id=_owner_display(owner), provider_tg_id=owner.provider_tg_id)
    except AdSlotError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


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
