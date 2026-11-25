"""AdMaven TMA task adapter с EFHC-owned CLICK_ID/postback correlation."""

from __future__ import annotations

from typing import Any

from app.integrations.ads.base import (
    AdContext,
    ProviderPreparation,
    ProviderVerification,
)
from app.integrations.ads.common import (
    basic_eligibility,
    make_signed_correlation,
    normalized_provider_error,
    verify_signed_correlation,
)
from app.services.ads.config_service import ProviderRuntimeConfig


class AdMavenAdapter:
    code = "admaven"

    def is_configured(self, config: ProviderRuntimeConfig) -> bool:
        return bool(config.is_configured())

    def is_eligible(self, config: ProviderRuntimeConfig, context: AdContext, *, surface: str = "miniapp") -> tuple[bool, str | None]:
        eligible, reason = basic_eligibility(config, context, surface=surface)
        return bool(eligible), str(reason) if reason is not None else None

    async def prepare(self, config: ProviderRuntimeConfig, context: AdContext, *, session_id: str, task_code: str, placement: str | None = None, required_format: str = "rewarded") -> ProviderPreparation:
        _ = context, task_code, placement, required_format
        correlation = make_signed_correlation(session_id, str(config.secret.get("postback_secret") or ""))
        return ProviderPreparation(
            provider=self.code,
            provider_ref=session_id,
            public_config={
                "adapter": "admaven",
                "format": "task_reward",
                "script_src": str(config.public["script_src"]),
                "postback_value": correlation,
            },
        )

    async def verify_callback(self, config: ProviderRuntimeConfig, payload: dict[str, Any], *, session_id: str) -> ProviderVerification:
        click_id = str(payload.get("click_id") or payload.get("CLICK_ID") or payload.get("postback_value") or "")
        verified = verify_signed_correlation(
            click_id,
            session_id,
            str(config.secret.get("postback_secret") or ""),
        )
        return ProviderVerification(
            provider=self.code,
            provider_event_id=str(payload.get("event_id") or click_id or f"admaven:{session_id}"),
            verified=verified,
            completed=verified,
            metadata={"source": "server_postback"},
        )

    def normalize_error(self, error: object) -> str:
        return str(normalized_provider_error(error))
