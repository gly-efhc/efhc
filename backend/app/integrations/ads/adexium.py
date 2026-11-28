"""Adexium TMA widget adapter с server task-check после SDK completion."""

from __future__ import annotations

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
    normalized_provider_error,
)
from app.services.ads.config_service import ProviderRuntimeConfig


class AdexiumAdapter:
    code = "adexium"

    def is_configured(self, config: ProviderRuntimeConfig) -> bool:
        return bool(config.is_configured())

    def is_eligible(self, config: ProviderRuntimeConfig, context: AdContext, *, surface: str = "miniapp") -> tuple[bool, str | None]:
        eligible, reason = basic_eligibility(config, context, surface=surface)
        return bool(eligible), str(reason) if reason is not None else None

    async def prepare(self, config: ProviderRuntimeConfig, context: AdContext, *, session_id: str, task_code: str, placement: str | None = None, required_format: str = "rewarded") -> ProviderPreparation:
        _ = context, task_code, required_format
        return ProviderPreparation(
            provider=self.code,
            provider_ref=session_id,
            public_config={
                "adapter": "adexium",
                "format": "interstitial",
                "widget_id": str(placement or config.public["widget_id"]),
                "sdk_src": str(config.public["sdk_src"]),
                "manual_mode": True,
                "correlation_id": session_id,
            },
        )

    async def verify_callback(self, config: ProviderRuntimeConfig, payload: dict[str, Any], *, session_id: str) -> ProviderVerification:
        task_id = str(payload.get("provider_task_id") or "").strip()
        if not task_id or not bool(payload.get("completed", False)):
            return ProviderVerification(self.code, task_id or f"adexium:{session_id}", False, False)
        widget = str(config.public["widget_id"])
        endpoint = f"https://bid.tgads.live/task/check/{widget}/{task_id}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(float(get_settings().ADS_PROVIDER_TIMEOUT_SEC))) as client:
            response = await client.get(endpoint)
            response.raise_for_status()
            data = response.json()
        verified = bool(
            data is True
            or (
                isinstance(data, dict)
                and (
                    data.get("done") is True
                    or data.get("completed") is True
                    or data.get("success") is True
                    or data.get("status") in {"completed", "done", "success"}
                )
            )
        )
        return ProviderVerification(
            provider=self.code,
            provider_event_id=task_id,
            verified=verified,
            completed=verified,
            metadata={"source": "provider_task_check"},
        )

    def normalize_error(self, error: object) -> str:
        return str(normalized_provider_error(error))
