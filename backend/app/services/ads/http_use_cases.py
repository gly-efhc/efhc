"""Advertising use cases formerly implemented in HTTP routes."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from app.core.config_core import get_settings
from app.core.decimal_utils import d8
from app.crud import ads_http_crud
from app.identity.telegram_auth_session import resolve_telegram_subject_global_id
from app.integrations.ads_providers import issue_builtin_timer_token
from app.lib.time import utcnow
from app.schemas.ads_schemas import AdSlotOut
from app.services.ads.config_service import load_provider_config
from sqlalchemy.ext.asyncio import AsyncSession

settings = get_settings()
ACTIVE_LANGUAGES = frozenset({"en", "ru", "uk", "de", "fr", "es", "it", "tr", "pl", "da", "hi", "id", "sw", "pt", "ko", "ja"})


class AdSlotError(ValueError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


async def stored_language(db: AsyncSession, *, global_id: int) -> str | None:
    row = await ads_http_crud.read_user_language_metadata(db, global_id=global_id)
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


async def record_adsgram_reward_url_signal(db: AsyncSession, *, provider_tg_id: int) -> dict[str, Any]:
    """Record correlation telemetry only; never issue EFHCb."""
    global_id = await resolve_telegram_subject_global_id(db, provider_tg_id)
    if global_id is None:
        return {"ok": True, "matched": False}
    cutoff = utcnow() - timedelta(minutes=30)
    session = await ads_http_crud.find_recent_adsgram_session(db, global_id=global_id.value, cutoff=cutoff)
    if session is None:
        return {"ok": True, "matched": False}
    provider_event_id = f"adsgram-reward-url:{session.session_id}"
    existing = await ads_http_crud.find_adsgram_reward_signal(db, provider_event_id=provider_event_id)
    if existing is None:
        ads_http_crud.add_adsgram_reward_signal(db, session=session, provider_event_id=provider_event_id)
        await db.commit()
    return {"ok": True, "matched": True}


async def get_compat_slot(db: AsyncSession, *, task_code: str, provider: str | None, global_id: str, provider_tg_id: int | None) -> AdSlotOut:
    task = await ads_http_crud.find_ad_task(db, task_code=task_code)
    if task is None:
        raise AdSlotError(404, "Задание не найдено")
    if not task.active or task.type != "watch_ad":
        raise AdSlotError(409, "NOT_SUPPORTED")
    selected = str(provider or "adsgram").strip().lower()
    bonus = d8(task.bonus_efhc or Decimal("0"))

    if selected == "builtin_timer":
        if not bool(settings.ADS_TEST_MODE) or not bool(settings.ADS_BUILTIN_TIMER_ENABLED):
            raise AdSlotError(410, "NOT_SUPPORTED")
        if provider_tg_id is None:
            raise AdSlotError(409, "telegram_provider_required")
        token = issue_builtin_timer_token(
            tg_id=provider_tg_id,
            task_code=task_code,
            bonus_efhc=bonus,
            ttl_sec=int(settings.ADS_BUILTIN_TOKEN_TTL_SEC),
        )
        return AdSlotOut(
            provider="builtin_timer",
            task_code=task_code,
            global_id=global_id,
            bonus_efhc=str(bonus),
            token=token,
            expires_at=(utcnow() + timedelta(seconds=int(settings.ADS_BUILTIN_TOKEN_TTL_SEC))).isoformat(),
            min_view_sec=int(settings.ADS_BUILTIN_MIN_VIEW_SEC),
        )

    if selected != "adsgram":
        raise AdSlotError(410, "USE_AD_MANAGER_SESSION")
    config = await load_provider_config(db, "adsgram")
    if not config.enabled or not config.is_configured():
        raise AdSlotError(409, "NOT_CONFIGURED")
    return AdSlotOut(
        provider="adsgram",
        task_code=task_code,
        global_id=global_id,
        bonus_efhc=str(bonus),
        placement_id=str(config.public.get("reward_block_id") or "") or None,
    )
