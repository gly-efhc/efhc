"""Адаптер RichAds Telegram SSP для interstitial-video."""

from __future__ import annotations

from contextlib import suppress
from typing import Any

import httpx
from app.core.config_core import get_settings
from app.integrations.ads.base import (
    AdContext,
    ProviderPreparation,
    ProviderVerification,
)
from app.integrations.ads.common import (
    basic_eligibility,
    decimal_or_none,
    normalized_provider_error,
)
from app.services.ads.config_service import ProviderRuntimeConfig


class RichAdsAdapter:
    code = "richads"

    def is_configured(self, config: ProviderRuntimeConfig) -> bool:
        return bool(config.is_configured())

    def is_eligible(self, config: ProviderRuntimeConfig, context: AdContext, *, surface: str = "miniapp") -> tuple[bool, str | None]:
        ok, reason = basic_eligibility(config, context, surface=surface)
        if not ok:
            return ok, reason
        if not context.ip_address or not context.user_agent:
            return False, "NOT_SUPPORTED"
        return True, None

    async def prepare(self, config: ProviderRuntimeConfig, context: AdContext, *, session_id: str, task_code: str, placement: str | None = None, required_format: str = "rewarded") -> ProviderPreparation:
        _ = task_code, required_format
        payload: dict[str, Any] = {
            "ip": str(context.ip_address),
            "user_agent": str(context.user_agent),
            "publisher_id": str(config.public["publisher_id"]),
            "motivated": True,
            "language_code": str(context.app_language)[:2].lower(),
            "production": not context.test_mode,
            "number_of_bids": 1,
        }
        widget_id = str(placement or config.public.get("widget_id") or "").strip()
        if widget_id:
            payload["widget_id"] = widget_id
        if config.public.get("bid_floor") not in (None, ""):
            with suppress(ValueError):
                payload["bid_floor"] = float(str(config.public["bid_floor"]))
        if context.provider_tg_id is not None:
            payload["telegram_id"] = str(context.provider_tg_id)
        if context.telegram_premium is not None:
            payload["premium"] = bool(context.telegram_premium)

        endpoint = f"http://{str(config.public['ssp_id']).strip()}.xml.adx1.com/telegram-bid"
        timeout = httpx.Timeout(float(get_settings().ADS_PROVIDER_TIMEOUT_SEC))
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(endpoint, json=payload)
            response.raise_for_status()
            body = response.json()
        if not isinstance(body, list) or not body or not isinstance(body[0], dict):
            raise ValueError("NO_FILL")
        creative = dict(body[0])
        public_creative = {
            key: creative.get(key)
            for key in (
                "title", "message", "video", "banner", "icon", "image_preload",
                "notification_url", "link", "brand", "button", "bid_price", "width", "height",
            )
            if creative.get(key) is not None
        }
        provider_ref = str(
            creative.get("creative_id")
            or creative.get("notification_url")
            or creative.get("link")
            or session_id
        )
        return ProviderPreparation(
            provider=self.code,
            provider_ref=provider_ref,
            estimated_revenue_usd=decimal_or_none(creative.get("bid_price")),
            public_config={
                "adapter": "richads",
                "format": "interstitial_video",
                "creative": public_creative,
            },
        )

    async def verify_callback(self, config: ProviderRuntimeConfig, payload: dict[str, Any], *, session_id: str) -> ProviderVerification:
        _ = config
        completed = bool(payload.get("completed", False))
        return ProviderVerification(
            provider=self.code,
            provider_event_id=str(payload.get("event_id") or f"richads-client:{session_id}"),
            verified=completed,
            completed=completed,
            valued=None,
            estimated_revenue_usd=decimal_or_none(payload.get("estimated_price")),
            metadata={"source": "client_completion_after_server_bid"},
        )

    def normalize_error(self, error: object) -> str:
        return str(normalized_provider_error(error))
