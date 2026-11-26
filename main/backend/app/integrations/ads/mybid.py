"""MyBid Rewarded Video adapter foundation без выдуманного callback contract."""

from __future__ import annotations

from typing import Any

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


class MyBidAdapter:
    code = "mybid"

    def is_configured(self, config: ProviderRuntimeConfig) -> bool:
        return bool(config.is_configured())

    def is_eligible(self, config: ProviderRuntimeConfig, context: AdContext, *, surface: str = "miniapp") -> tuple[bool, str | None]:
        eligible, reason = basic_eligibility(config, context, surface=surface)
        if not eligible:
            return eligible, reason
        # FAIL-CLOSED: публично подтверждённого reward-verification/callback
        # контракта для production EFHCb в текущем handoff нет. Сам Widget ID
        # не является доказательством просмотра и не даёт права выбирать сеть
        # в rewarded mediation. После получения официального cabinet contract
        # adapter расширяется отдельно, без изменений Tasks/AdManager.
        return False, "NOT_SUPPORTED"

    async def prepare(self, config: ProviderRuntimeConfig, context: AdContext, *, session_id: str, task_code: str, placement: str | None = None, required_format: str = "rewarded") -> ProviderPreparation:
        _ = context, task_code, required_format
        return ProviderPreparation(
            provider=self.code,
            provider_ref=session_id,
            public_config={
                "adapter": "mybid",
                "format": "rewarded_video",
                "widget_id": str(placement or config.public["widget_id"]),
                "sdk_src": str(config.public["sdk_src"]),
                "correlation_id": session_id,
                "verification_contract": "publisher_cabinet_required",
            },
        )

    async def verify_callback(self, config: ProviderRuntimeConfig, payload: dict[str, Any], *, session_id: str) -> ProviderVerification:
        _ = config, payload
        return ProviderVerification(self.code, f"mybid-unverified:{session_id}", False, False)

    def normalize_error(self, error: object) -> str:
        return str(normalized_provider_error(error))
