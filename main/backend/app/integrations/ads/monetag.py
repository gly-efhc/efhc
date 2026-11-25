"""Monetag Rewarded adapter: SDK correlation через ymid + server postback."""

from __future__ import annotations

from typing import Any

from app.integrations.ads.base import (
    AdContext,
    ProviderPreparation,
    ProviderVerification,
)
from app.integrations.ads.common import (
    basic_eligibility,
    decimal_or_none,
    make_signed_correlation,
    normalized_provider_error,
    verify_signed_correlation,
)
from app.services.ads.config_service import ProviderRuntimeConfig


class MonetagAdapter:
    code = "monetag"

    def is_configured(self, config: ProviderRuntimeConfig) -> bool:
        return bool(config.is_configured())

    def is_eligible(self, config: ProviderRuntimeConfig, context: AdContext, *, surface: str = "miniapp") -> tuple[bool, str | None]:
        eligible, reason = basic_eligibility(config, context, surface=surface)
        return bool(eligible), str(reason) if reason is not None else None

    async def prepare(self, config: ProviderRuntimeConfig, context: AdContext, *, session_id: str, task_code: str, placement: str | None = None, required_format: str = "rewarded") -> ProviderPreparation:
        _ = context, required_format
        zone_id = str(placement or config.public["rewarded_zone_id"])
        ymid = make_signed_correlation(session_id, str(config.secret.get("postback_secret") or ""))
        return ProviderPreparation(
            provider=self.code,
            provider_ref=session_id,
            public_config={
                "adapter": "monetag",
                "format": "rewarded_interstitial",
                "zone_id": zone_id,
                "show_function": f"show_{zone_id}",
                "sdk_src": str(config.public.get("sdk_src") or ""),
                "ymid": ymid,
                "request_var": f"efhc:{task_code}",
                "catch_if_no_feed": True,
                "preload": True,
            },
        )

    async def verify_callback(self, config: ProviderRuntimeConfig, payload: dict[str, Any], *, session_id: str) -> ProviderVerification:
        _ = config
        ymid = str(payload.get("ymid") or "")
        if not verify_signed_correlation(ymid, session_id, str(config.secret.get("postback_secret") or "")):
            return ProviderVerification(self.code, str(payload.get("event_id") or ymid or "missing"), False, False)
        reward_event_type = str(payload.get("reward_event_type") or payload.get("value") or "").lower()
        event_type = str(payload.get("event_type") or payload.get("event") or "impression").lower()
        valued = reward_event_type == "valued"
        return ProviderVerification(
            provider=self.code,
            provider_event_id=str(payload.get("event_id") or f"{ymid}:{event_type}"),
            verified=valued,
            completed=valued,
            valued=valued,
            estimated_revenue_usd=decimal_or_none(payload.get("estimated_price") or payload.get("price")),
            metadata={
                "event_type": event_type,
                "reward_event_type": reward_event_type,
                "zone_id": payload.get("zone_id") or payload.get("zone"),
                "sub_zone_id": payload.get("sub_zone_id") or payload.get("sub"),
            },
        )

    def normalize_error(self, error: object) -> str:
        return str(normalized_provider_error(error))
